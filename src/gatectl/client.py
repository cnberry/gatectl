from __future__ import annotations

import json
from typing import Mapping
from urllib.parse import quote

from .auth import MyQAuth
from .constants import (
    ACCOUNTS_BASE_URL,
    APP_VERSION,
    BRAND_ID,
    DEVICES_BASE_URL,
    GARAGE_DEVICES_BASE_URL,
    USER_AGENT,
)
from .errors import MyQApiError, MyQAuthenticationError
from .http import HttpResponse, HttpSession
from .models import MyQAccount, MyQDevice, parse_account, parse_device


class MyQClient:
    """MyQ account, device-status, and guarded garage-door client."""

    def __init__(self, session: HttpSession, auth: MyQAuth) -> None:
        self._session = session
        self._auth = auth

    def get_accounts(self) -> tuple[MyQAccount, ...]:
        payload = self._request_json("GET", f"{ACCOUNTS_BASE_URL}/api/v6.0/accounts")
        raw_accounts = payload.get("accounts")
        if not isinstance(raw_accounts, list):
            raise MyQApiError("MyQ account discovery returned no account list")
        accounts: list[MyQAccount] = []
        for raw in raw_accounts:
            if not isinstance(raw, dict):
                raise MyQApiError("MyQ returned an invalid account")
            accounts.append(parse_account(raw))
        return tuple(accounts)

    def get_devices(self, accounts: tuple[MyQAccount, ...] | None = None) -> tuple[MyQDevice, ...]:
        account_list = accounts if accounts is not None else self.get_accounts()
        devices: list[MyQDevice] = []
        for account in account_list:
            payload = self._request_json(
                "GET",
                f"{DEVICES_BASE_URL}/api/v6.2/Accounts/{account.account_id}/Devices",
            )
            raw_items = payload.get("items")
            if not isinstance(raw_items, list):
                raise MyQApiError(f"MyQ device discovery returned no items for {account.name}")
            for raw in raw_items:
                if not isinstance(raw, dict):
                    raise MyQApiError("MyQ returned an invalid device")
                devices.append(parse_device(account, raw))
        return tuple(devices)

    def open_device(self, device: MyQDevice) -> bool:
        """Open one exact, online garage-door device.

        Return False without sending a command when MyQ already reports the
        device open or opening. Other ambiguous states fail closed.
        """
        return self._command_device(device, "open")

    def close_device(self, device: MyQDevice) -> bool:
        """Close one exact, online garage-door device.

        Return False without sending a command when MyQ already reports the
        device closed or closing. Other ambiguous states fail closed.
        """
        return self._command_device(device, "close")

    def _command_device(self, device: MyQDevice, action: str) -> bool:
        if action not in {"open", "close"}:
            raise MyQApiError(f"Unsupported garage-door action: {action}")
        if device.device_family != "garagedoor":
            raise MyQApiError(f"{device.name} is not a garage-door device")
        if device.online is not True:
            raise MyQApiError(f"{device.name} is not online")

        target_state = action
        intermediate_state = "opening" if action == "open" else "closing"
        required_state = "closed" if action == "open" else "open"
        if device.door_state in {target_state, intermediate_state}:
            return False
        if device.door_state != required_state:
            raise MyQApiError(
                f"{device.name} is in state {device.door_state or 'unknown'}; refusing to {action}"
            )
        if device.state.get(f"is_unattended_{action}_allowed") is not True:
            raise MyQApiError(f"MyQ does not allow unattended {action}ing for {device.name}")

        account_id = quote(device.account_id, safe="")
        serial_number = quote(device.serial_number, safe="")
        self._request(
            "PUT",
            f"{GARAGE_DEVICES_BASE_URL}/api/v6.0/accounts/{account_id}/"
            f"door_openers/{serial_number}/{action}",
        )
        return True

    def _request_json(self, method: str, url: str) -> dict[str, object]:
        response = self._request(method, url)
        try:
            payload = json.loads(response.body)
        except json.JSONDecodeError as error:
            raise MyQApiError("MyQ returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise MyQApiError("MyQ returned an unexpected JSON response")
        return payload

    def _request(self, method: str, url: str) -> HttpResponse:
        is_guarded_command = (
            method == "PUT"
            and url.startswith(f"{GARAGE_DEVICES_BASE_URL}/api/v6.0/accounts/")
            and url.endswith(("/open", "/close"))
        )
        if method != "GET" and not is_guarded_command:
            raise MyQApiError("gatectl refused an unsupported MyQ write request")
        response = self._session.request(
            method,
            url,
            headers=_api_headers(self._auth.access_token()),
        )
        if response.status in {401, 403}:
            tokens = self._auth.refresh()
            response = self._session.request(
                method,
                url,
                headers=_api_headers(tokens.access_token),
            )
        if response.status in {401, 403}:
            raise MyQAuthenticationError(f"MyQ returned HTTP {response.status}")
        if not 200 <= response.status < 300:
            raise MyQApiError(f"MyQ returned HTTP {response.status}")
        return response


def _api_headers(access_token: str) -> Mapping[str, str]:
    return {
        "Accept": "application/json",
        "App-Version": APP_VERSION,
        "Authorization": f"Bearer {access_token}",
        "BrandId": BRAND_ID,
        "User-Agent": USER_AGENT,
    }
