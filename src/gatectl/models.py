from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import MyQApiError

SAFE_STATE_FIELDS = frozenset(
    {
        "absolute_cycle_count",
        "active_fault_codes",
        "attached_work_light_error_present",
        "attached_worklight_on",
        "battery_backup_state",
        "door_state",
        "dps_battery_critical",
        "dps_low_battery_mode",
        "dps_no_communication",
        "firmware_version",
        "in_vacation_mode",
        "is_scheduling_allowed",
        "is_unattended_close_allowed",
        "is_unattended_open_allowed",
        "last_status",
        "last_update",
        "learn_mode",
        "learn_status",
        "mandatory_update_required",
        "monitor_only_mode",
        "online",
        "pending_bootload_abandoned",
        "sensor_comm_error",
        "service_cycle_count",
        "supports_dealer_diagnostics",
        "wifi_signal_strength",
    }
)


@dataclass(frozen=True, slots=True)
class OAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: float

    def as_dict(self) -> dict[str, str | float]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> OAuthTokens:
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_at = data.get("expires_at")
        if not isinstance(access_token, str) or not access_token:
            raise MyQApiError("Stored MyQ access token is invalid")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise MyQApiError("Stored MyQ refresh token is invalid")
        if not isinstance(expires_at, int | float):
            raise MyQApiError("Stored MyQ token expiry is invalid")
        return cls(access_token, refresh_token, float(expires_at))


@dataclass(frozen=True, slots=True)
class MyQAccount:
    account_id: str
    name: str


@dataclass(frozen=True, slots=True)
class MyQDevice:
    account_id: str
    account_name: str
    serial_number: str
    name: str
    device_family: str
    device_model: str | None
    state: Mapping[str, Any]

    @property
    def door_state(self) -> str | None:
        value = self.state.get("door_state")
        return value if isinstance(value, str) else None

    @property
    def online(self) -> bool | None:
        value = self.state.get("online")
        return value if isinstance(value, bool) else None

    @property
    def redacted_serial(self) -> str:
        if len(self.serial_number) <= 4:
            return "****"
        return f"...{self.serial_number[-4:]}"

    def safe_dict(self, *, include_serial: bool = False) -> dict[str, object]:
        return {
            "account": self.account_name,
            "name": self.name,
            "family": self.device_family,
            "model": self.device_model,
            "serial": self.serial_number if include_serial else self.redacted_serial,
            "state": {key: value for key, value in self.state.items() if key in SAFE_STATE_FIELDS},
        }


def parse_account(raw: Mapping[str, object]) -> MyQAccount:
    account_id = raw.get("id")
    name = raw.get("name")
    if not isinstance(account_id, str) or not account_id:
        raise MyQApiError("MyQ returned an account without an ID")
    return MyQAccount(account_id, name if isinstance(name, str) else account_id)


def parse_device(account: MyQAccount, raw: Mapping[str, object]) -> MyQDevice:
    identifier = next(
        (
            value
            for value in (raw.get("serial_number"), raw.get("id"), raw.get("device_id"))
            if isinstance(value, str) and value
        ),
        None,
    )
    name = raw.get("name")
    family = raw.get("device_family")
    model = raw.get("device_model")
    state = raw.get("state")
    if identifier is None:
        raise MyQApiError("MyQ returned a device without an identifier")
    if state is not None and not isinstance(state, dict):
        raise MyQApiError(f"MyQ returned invalid state for {name or identifier}")
    return MyQDevice(
        account_id=account.account_id,
        account_name=account.name,
        serial_number=identifier,
        name=name if isinstance(name, str) else identifier,
        device_family=family if isinstance(family, str) else "unknown",
        device_model=model if isinstance(model, str) else None,
        state=state or {},
    )
