from __future__ import annotations

import unittest

from gatectl.client import MyQClient
from gatectl.http import HttpResponse
from gatectl.models import MyQAccount, MyQDevice, OAuthTokens


class FakeAuth:
    def access_token(self) -> str:
        return "access"

    def refresh(self) -> OAuthTokens:
        return OAuthTokens("refreshed", "refresh", 9999999999)


class FakeSession:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def request(self, method: str, url: str, **kwargs: object) -> HttpResponse:
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class ClientTests(unittest.TestCase):
    def test_discovers_accounts_hubs_and_target_devices(self) -> None:
        session = FakeSession(
            [
                HttpResponse(
                    "https://accounts/api/v6.0/accounts",
                    200,
                    {},
                    '{"accounts":[{"id":"account-1","name":"Demo Home"}]}',
                ),
                HttpResponse(
                    "https://devices/api/v6.2/Accounts/account-1/Devices",
                    200,
                    {},
                    """{
                      "items": [
                        {"device_family":"gateway","serial_number":"hub-1","name":"Main Hub","state":{"online":true}},
                        {"device_family":"gateway","serial_number":"hub-2","name":"Secondary Hub","state":{"online":true}},
                        {"device_family":"garagedoor","serial_number":"door-1","name":"Driveway Gate","device_model":"gate-operator","state":{"door_state":"closed","online":true}},
                        {"device_family":"garagedoor","serial_number":"door-2","name":"Garage Door","device_model":"garage-opener","state":{"door_state":"open","online":true}}
                      ]
                    }""",
                ),
            ]
        )
        client = MyQClient(session, FakeAuth())  # type: ignore[arg-type]

        accounts = client.get_accounts()
        devices = client.get_devices(accounts)

        self.assertEqual(accounts[0].name, "Demo Home")
        self.assertEqual(
            [device.name for device in devices],
            ["Main Hub", "Secondary Hub", "Driveway Gate", "Garage Door"],
        )
        self.assertEqual(devices[2].door_state, "closed")
        self.assertEqual(devices[3].door_state, "open")
        self.assertTrue(all(call[0] == "GET" for call in session.calls))

    def test_accepts_hub_id_when_serial_number_is_absent(self) -> None:
        session = FakeSession(
            [
                HttpResponse(
                    "https://devices/api/v6.2/Accounts/account-1/Devices",
                    200,
                    {},
                    '{"items":[{"id":"hub-id","device_family":"gateway","name":"Main Hub","state":{}}]}',
                )
            ]
        )
        client = MyQClient(session, FakeAuth())  # type: ignore[arg-type]

        devices = client.get_devices((MyQAccount("account-1", "Demo Home"),))

        self.assertEqual(devices[0].serial_number, "hub-id")

    def test_open_device_uses_guarded_current_command_endpoint(self) -> None:
        session = FakeSession([HttpResponse("https://gdo/open", 202, {}, "")])
        client = MyQClient(session, FakeAuth())  # type: ignore[arg-type]
        door = MyQDevice(
            "account-1",
            "Demo Home",
            "door/1",
            "Garage Door",
            "garagedoor",
            "wifigaragedooropener",
            {
                "door_state": "closed",
                "online": True,
                "is_unattended_open_allowed": True,
            },
        )

        sent = client.open_device(door)

        self.assertTrue(sent)
        self.assertEqual(session.calls[0][0], "PUT")
        self.assertEqual(
            session.calls[0][1],
            "https://account-devices-gdo.myq-cloud.com/api/v6.0/"
            "accounts/account-1/door_openers/door%2F1/open",
        )
        headers = session.calls[0][2]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer access")

    def test_open_device_refuses_when_unattended_open_is_not_allowed(self) -> None:
        session = FakeSession([])
        client = MyQClient(session, FakeAuth())  # type: ignore[arg-type]
        door = MyQDevice(
            "account-1",
            "Demo Home",
            "door-1",
            "Garage Door",
            "garagedoor",
            None,
            {"door_state": "closed", "online": True},
        )

        with self.assertRaisesRegex(Exception, "does not allow unattended opening"):
            client.open_device(door)

        self.assertEqual(session.calls, [])

    def test_close_device_uses_guarded_current_command_endpoint(self) -> None:
        session = FakeSession([HttpResponse("https://gdo/close", 202, {}, "")])
        client = MyQClient(session, FakeAuth())  # type: ignore[arg-type]
        door = MyQDevice(
            "account-1",
            "Demo Home",
            "door-1",
            "Garage Door",
            "garagedoor",
            "wifigaragedooropener",
            {
                "door_state": "open",
                "online": True,
                "is_unattended_close_allowed": True,
            },
        )

        sent = client.close_device(door)

        self.assertTrue(sent)
        self.assertEqual(session.calls[0][0], "PUT")
        self.assertEqual(
            session.calls[0][1],
            "https://account-devices-gdo.myq-cloud.com/api/v6.0/"
            "accounts/account-1/door_openers/door-1/close",
        )

    def test_commands_are_idempotent_when_already_at_target(self) -> None:
        session = FakeSession([])
        client = MyQClient(session, FakeAuth())  # type: ignore[arg-type]
        common = ("account-1", "Demo Home", "door-1", "Garage Door", "garagedoor", None)
        open_door = MyQDevice(
            *common,
            {"door_state": "open", "online": True, "is_unattended_open_allowed": True},
        )
        closing_door = MyQDevice(
            *common,
            {"door_state": "closing", "online": True, "is_unattended_close_allowed": True},
        )

        self.assertFalse(client.open_device(open_door))
        self.assertFalse(client.close_device(closing_door))
        self.assertEqual(session.calls, [])

    def test_command_retries_once_with_refreshed_token(self) -> None:
        session = FakeSession(
            [
                HttpResponse("https://gdo/open", 401, {}, ""),
                HttpResponse("https://gdo/open", 202, {}, ""),
            ]
        )
        client = MyQClient(session, FakeAuth())  # type: ignore[arg-type]
        door = MyQDevice(
            "account-1",
            "Demo Home",
            "door-1",
            "Garage Door",
            "garagedoor",
            None,
            {
                "door_state": "closed",
                "online": True,
                "is_unattended_open_allowed": True,
            },
        )

        self.assertTrue(client.open_device(door))
        self.assertEqual(len(session.calls), 2)
        first_headers = session.calls[0][2]["headers"]
        second_headers = session.calls[1][2]["headers"]
        self.assertEqual(first_headers["Authorization"], "Bearer access")
        self.assertEqual(second_headers["Authorization"], "Bearer refreshed")

    def test_command_refuses_ambiguous_state_and_arbitrary_writes(self) -> None:
        session = FakeSession([])
        client = MyQClient(session, FakeAuth())  # type: ignore[arg-type]
        stopped = MyQDevice(
            "account-1",
            "Demo Home",
            "door-1",
            "Garage Door",
            "garagedoor",
            None,
            {
                "door_state": "stopped",
                "online": True,
                "is_unattended_close_allowed": True,
            },
        )

        with self.assertRaisesRegex(Exception, "refusing to close"):
            client.close_device(stopped)
        with self.assertRaisesRegex(Exception, "unsupported MyQ write"):
            client._request("DELETE", "https://example.invalid/device")  # noqa: SLF001
        self.assertEqual(session.calls, [])

    def test_safe_output_drops_nested_transmitter_and_source_identifiers(self) -> None:
        door = MyQDevice(
            "account-1",
            "Demo Home",
            "serial-1234",
            "Garage Door",
            "garagedoor",
            None,
            {
                "door_state": "closed",
                "online": True,
                "last_update": "2026-01-01T00:00:00Z",
                "eserial_transmitters": {"private-transmitter": {"enabled": True}},
                "last_device_activation_source_id": "private-source",
            },
        )

        safe = door.safe_dict()

        self.assertEqual(safe["serial"], "...1234")
        self.assertEqual(
            safe["state"],
            {
                "door_state": "closed",
                "online": True,
                "last_update": "2026-01-01T00:00:00Z",
            },
        )

    def test_command_does_not_treat_redirect_as_acceptance(self) -> None:
        session = FakeSession(
            [HttpResponse("https://identity/challenge", 302, {"Location": "/login"}, "")]
        )
        client = MyQClient(session, FakeAuth())  # type: ignore[arg-type]
        door = MyQDevice(
            "account-1",
            "Demo Home",
            "door-1",
            "Garage Door",
            "garagedoor",
            None,
            {
                "door_state": "closed",
                "online": True,
                "is_unattended_open_allowed": True,
            },
        )

        with self.assertRaisesRegex(Exception, "HTTP 302"):
            client.open_device(door)


if __name__ == "__main__":
    unittest.main()
