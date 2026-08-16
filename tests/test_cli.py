from __future__ import annotations

import itertools
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gatectl.cli import _close
from gatectl.models import MyQAccount, MyQDevice


def _door(state: str) -> MyQDevice:
    return MyQDevice(
        "account-1",
        "Demo Home",
        "door-1",
        "Garage Door",
        "garagedoor",
        "garage-opener",
        {
            "door_state": state,
            "online": True,
            "is_unattended_close_allowed": True,
        },
    )


class FakeClient:
    def __init__(self, states: tuple[str, ...]) -> None:
        self._batches = [(_door(state),) for state in states]
        self.closed: list[MyQDevice] = []

    def get_accounts(self) -> tuple[MyQAccount, ...]:
        return (MyQAccount("account-1", "Demo Home"),)

    def get_devices(
        self,
        accounts: tuple[MyQAccount, ...],
    ) -> tuple[MyQDevice, ...]:
        del accounts
        return self._batches.pop(0)

    def close_device(self, device: MyQDevice) -> bool:
        self.closed.append(device)
        return True


class CliOperationTests(unittest.TestCase):
    def test_close_waits_until_closed(self) -> None:
        client = FakeClient(("open", "closing", "closed"))
        ticks = itertools.count()
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "targets.json"
            config.write_text(
                '{"account":"Demo Home","devices":["Garage Door"]}',
                encoding="utf-8",
            )
            with (
                patch("gatectl.cli._client", return_value=client),
                patch("gatectl.cli._save_observation"),
                patch("gatectl.cli.time.sleep"),
                patch("gatectl.cli.time.monotonic", side_effect=lambda: float(next(ticks))),
                patch("builtins.print"),
            ):
                result = _close("Garage Door", True, 10, config)

        self.assertEqual(result, 0)
        self.assertEqual([door.door_state for door in client.closed], ["open"])

    def test_noninteractive_close_requires_explicit_yes(self) -> None:
        client = FakeClient(("open",))
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "targets.json"
            config.write_text(
                '{"account":"Demo Home","devices":["Garage Door"]}',
                encoding="utf-8",
            )
            with (
                patch("gatectl.cli._client", return_value=client),
                patch("gatectl.cli._save_observation"),
                patch("gatectl.cli.sys.stdin.isatty", return_value=False),
            ):
                with self.assertRaisesRegex(ValueError, "rerun with --yes"):
                    _close("Garage Door", False, 10, config)

        self.assertEqual(client.closed, [])

    def test_zero_wait_returns_after_command_acceptance(self) -> None:
        client = FakeClient(("open",))
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "targets.json"
            config.write_text(
                '{"account":"Demo Home","devices":["Garage Door"]}',
                encoding="utf-8",
            )
            with (
                patch("gatectl.cli._client", return_value=client),
                patch("gatectl.cli._save_observation"),
                patch("builtins.print"),
            ):
                result = _close("Garage Door", True, 0, config)

        self.assertEqual(result, 0)
        self.assertEqual(len(client.closed), 1)


if __name__ == "__main__":
    unittest.main()
