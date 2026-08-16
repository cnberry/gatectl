from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from .auth import MyQAuth, MyQLoginSession
from .client import MyQClient
from .constants import MFA_METHOD_EMAIL, MFA_METHOD_SMS
from .errors import GatectlError
from .http import HttpSession
from .models import MyQAccount, MyQDevice
from .storage import load_tokens, save_observation, save_tokens, target_config_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gatectl",
        description="MyQ account, device-status, and guarded door commands",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Target config path (default: GATECTL_CONFIG or ~/.config/gatectl/targets.json)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check the current MyQ login flow anonymously")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    login = subparsers.add_parser("login", help="Create a local MyQ session")
    login.add_argument("--email", help="MyQ account email (or set MYQ_EMAIL)")
    login.add_argument(
        "--mfa",
        choices=(MFA_METHOD_EMAIL, MFA_METHOD_SMS),
        default=MFA_METHOD_EMAIL,
        help="Where MyQ should send the verification code",
    )

    inspect = subparsers.add_parser("inspect", help="List MyQ accounts, hubs, and devices")
    inspect.add_argument("--json", action="store_true", dest="as_json")
    inspect.add_argument("--show-serials", action="store_true")

    status = subparsers.add_parser("status", help="Read target device state")
    status.add_argument("names", nargs="*", help="Exact device names (defaults to saved targets)")
    status.add_argument("--json", action="store_true", dest="as_json")
    status.add_argument("--show-serials", action="store_true")

    open_door = subparsers.add_parser("open", help="Open one exact garage-door device")
    open_door.add_argument("name", help="Exact device name")
    open_door.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the physical open action without an interactive prompt",
    )
    open_door.add_argument(
        "--wait",
        type=float,
        default=45.0,
        metavar="SECONDS",
        help="How long to wait for MyQ to report open (default: 45)",
    )

    close_door = subparsers.add_parser("close", help="Close one exact garage-door device")
    close_door.add_argument("name", help="Exact device name")
    close_door.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the physical close action without an interactive prompt",
    )
    close_door.add_argument(
        "--wait",
        type=float,
        default=60.0,
        metavar="SECONDS",
        help="How long to wait for MyQ to report closed (default: 60)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return _doctor(args.as_json)
        if args.command == "login":
            return _login(args.email, args.mfa)
        if args.command == "inspect":
            return _inspect(args.as_json, args.show_serials)
        if args.command == "status":
            return _status(args.names, args.as_json, args.show_serials, args.config)
        if args.command == "open":
            return _open(args.name, args.yes, args.wait, args.config)
        if args.command == "close":
            return _close(args.name, args.yes, args.wait, args.config)
    except (GatectlError, ValueError) as error:
        print(f"gatectl: {error}", file=sys.stderr)
        return 2
    return 2


def _doctor(as_json: bool) -> int:
    result = MyQLoginSession(HttpSession()).probe()
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("MyQ residential login is reachable and the expected sign-in form was found.")
        print(f"Path: {result['path']} (HTTP {result['http_status']})")
    return 0


def _login(email: str | None, mfa_method: str) -> int:
    email_address = email or os.environ.get("MYQ_EMAIL") or input("MyQ email: ").strip()
    if not email_address:
        raise ValueError("A MyQ email address is required")
    password = os.environ.get("MYQ_PASSWORD") or getpass.getpass("MyQ password: ")
    if not password:
        raise ValueError("A MyQ password is required")

    login = MyQLoginSession(HttpSession())
    tokens = login.start(email_address, password, mfa_method)
    if tokens is None:
        code = input(f"Enter the six-digit code sent by {mfa_method}: ").strip()
        if not code:
            raise ValueError("A MyQ verification code is required")
        tokens = login.submit_mfa(code)
    path = save_tokens(tokens)
    print(f"MyQ session saved with mode 0600 at {path}")
    print("No account password was stored.")
    return 0


def _client() -> MyQClient:
    session = HttpSession()
    tokens = load_tokens()
    auth = MyQAuth(session, tokens, save_tokens)
    return MyQClient(session, auth)


def _discover() -> tuple[tuple[MyQAccount, ...], tuple[MyQDevice, ...], Path]:
    client = _client()
    accounts = client.get_accounts()
    devices = client.get_devices(accounts)
    state_path = _save_observation(accounts, devices)
    return accounts, devices, state_path


def _inspect(as_json: bool, show_serials: bool) -> int:
    accounts, devices, state_path = _discover()
    result = {
        "accounts": [
            {
                "name": account.name,
                "devices": [
                    device.safe_dict(include_serial=show_serials)
                    for device in devices
                    if device.account_id == account.account_id
                ],
            }
            for account in accounts
        ],
        "saved_observation": str(state_path),
    }
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    for account in result["accounts"]:
        print(f"Account: {account['name']}")
        for device in account["devices"]:
            state = _state_text(device["state"])
            model = f" model={device['model']}" if device["model"] else ""
            print(
                f"  {device['name']}: family={device['family']}{model} "
                f"serial={device['serial']} {state}"
            )
    print(f"Sanitized observation saved at {state_path}")
    return 0


def _status(
    names: Sequence[str],
    as_json: bool,
    show_serials: bool,
    config_path: Path | None = None,
) -> int:
    target_account, saved_targets = load_target_config(config_path)
    targets = tuple(names) if names else saved_targets
    accounts, devices, state_path = _discover()
    matches = select_targets(devices, targets, account_name=target_account)
    account_found = any(
        account.name.casefold() == target_account.casefold() for account in accounts
    )
    result = {
        "target_account": target_account,
        "target_account_found": account_found,
        "targets": list(targets),
        "matches": [device.safe_dict(include_serial=show_serials) for device in matches],
        "saved_observation": str(state_path),
    }
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if not account_found:
            print(f"Account {target_account!r}: not found", file=sys.stderr)
        for device in matches:
            print(f"{device.account_name} / {device.name}: {_state_text(device.state)}")
        missing = [
            target
            for target in targets
            if target.casefold() not in {d.name.casefold() for d in matches}
        ]
        for target in missing:
            print(f"{target}: not found", file=sys.stderr)
        print(f"Observation saved at {state_path}")
    if not matches:
        return 4
    return 0 if any(device.door_state is not None for device in matches) else 5


def _open(
    name: str,
    confirmed: bool,
    wait_seconds: float,
    config_path: Path | None = None,
) -> int:
    return _operate(name, "open", confirmed, wait_seconds, config_path)


def _close(
    name: str,
    confirmed: bool,
    wait_seconds: float,
    config_path: Path | None = None,
) -> int:
    return _operate(name, "close", confirmed, wait_seconds, config_path)


def _operate(
    name: str,
    action: str,
    confirmed: bool,
    wait_seconds: float,
    config_path: Path | None = None,
) -> int:
    if wait_seconds < 0 or wait_seconds > 120:
        raise ValueError("--wait must be between 0 and 120 seconds")
    if action not in {"open", "close"}:
        raise ValueError(f"Unsupported door action: {action}")

    target_account, _ = load_target_config(config_path)
    client = _client()
    accounts = client.get_accounts()
    devices = client.get_devices(accounts)
    matches = select_targets(devices, (name,), account_name=target_account)
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one device named {name!r} in {target_account!r}; found {len(matches)}"
        )
    device = matches[0]
    _save_observation(accounts, devices)

    if not confirmed:
        if not sys.stdin.isatty():
            raise ValueError(f"Refusing to {action} without confirmation; rerun with --yes")
        answer = input(
            f"{action.title()} {device.account_name} / {device.name}? Type {action!r} to confirm: "
        ).strip()
        if answer.casefold() != action:
            raise ValueError(f"{action.title()} command cancelled")

    command = client.open_device if action == "open" else client.close_device
    sent = command(device)
    if not sent:
        print(f"{device.account_name} / {device.name}: already {device.door_state}")
        return 0
    print(f"{device.account_name} / {device.name}: {action} command accepted by MyQ")
    if wait_seconds == 0:
        print("State verification skipped (--wait 0)")
        return 0

    target_state = "open" if action == "open" else "closed"
    deadline = time.monotonic() + wait_seconds
    latest = device
    while time.monotonic() < deadline:
        time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
        devices = client.get_devices(accounts)
        matches = select_targets(devices, (name,), account_name=target_account)
        if len(matches) != 1:
            raise ValueError(f"Lost the exact device match for {name!r} while checking state")
        latest = matches[0]
        _save_observation(accounts, devices)
        print(f"{latest.account_name} / {latest.name}: {_state_text(latest.state)}")
        if latest.door_state == target_state:
            return 0

    raise ValueError(
        f"MyQ accepted the command, but {device.name} did not report {target_state} "
        f"within {wait_seconds:g} seconds "
        f"(last state: {latest.door_state or 'unknown'})"
    )


def select_targets(
    devices: Sequence[MyQDevice],
    targets: Sequence[str],
    *,
    account_name: str | None = None,
) -> tuple[MyQDevice, ...]:
    wanted = {target.casefold() for target in targets}
    wanted_account = account_name.casefold() if account_name is not None else None
    return tuple(
        device
        for device in devices
        if device.name.casefold() in wanted
        and (wanted_account is None or device.account_name.casefold() == wanted_account)
    )


def load_target_config(path: Path | None = None) -> tuple[str, tuple[str, ...]]:
    config_path = path.expanduser() if path is not None else target_config_path()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(
            f"No target config found at {config_path}; copy config/targets.example.json there"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to read target config at {config_path}") from error
    if not isinstance(raw, dict):
        raise ValueError(f"Target config at {config_path} must be a JSON object")
    raw_account = raw.get("account")
    if not isinstance(raw_account, str) or not raw_account.strip():
        raise ValueError(f"Target config at {config_path} requires a non-empty account")
    account = raw_account.strip()
    raw_devices = raw.get("devices")
    if not isinstance(raw_devices, list):
        raise ValueError(f"Target config at {config_path} requires a devices list")
    names = tuple(name.strip() for name in raw_devices if isinstance(name, str) and name.strip())
    if not names:
        raise ValueError(f"Target config at {config_path} requires at least one device")
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError(f"Target config at {config_path} contains duplicate device names")
    return account, names


def load_target_names(path: Path | None = None) -> tuple[str, ...]:
    return load_target_config(path)[1]


def _save_observation(
    accounts: Sequence[MyQAccount],
    devices: Sequence[MyQDevice],
) -> Path:
    return save_observation(
        {
            "observed_at": datetime.now(UTC).isoformat(),
            "accounts": [{"name": account.name} for account in accounts],
            "devices": [device.safe_dict() for device in devices],
        }
    )


def _state_text(state: object) -> str:
    if not isinstance(state, dict):
        return "state=unknown"
    door_state = state.get("door_state", "unknown")
    online = state.get("online")
    availability = (
        "online" if online is True else "offline" if online is False else "availability unknown"
    )
    return f"state={door_state} ({availability})"


if __name__ == "__main__":
    raise SystemExit(main())
