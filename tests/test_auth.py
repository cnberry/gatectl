from __future__ import annotations

import time
import unittest
from dataclasses import dataclass
from typing import Mapping

from gatectl.auth import MyQAuth, MyQLoginSession
from gatectl.constants import MFA_METHOD_EMAIL
from gatectl.http import HttpResponse
from gatectl.models import OAuthTokens


@dataclass(frozen=True)
class RecordedCall:
    method: str
    url: str
    kwargs: Mapping[str, object]


class FakeSession:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[RecordedCall] = []

    def request(self, method: str, url: str, **kwargs: object) -> HttpResponse:
        self.calls.append(RecordedCall(method, url, kwargs))
        if not self.responses:
            raise AssertionError(f"Unexpected request: {method} {url}")
        return self.responses.pop(0)


LOGIN_HTML = """
<form method="post" action="/Account/Login?returnUrl=auth">
  <input type="hidden" name="__RequestVerificationToken" value="csrf-login">
  <input type="email" name="Email">
  <input type="password" name="Password">
</form>
"""

MFA_HTML = """
<form method="post" action="/AccountMfa/VerifyOtp?returnUrl=auth">
  <input type="hidden" name="__RequestVerificationToken" value="csrf-mfa">
  <input type="hidden" name="SelectedMfaMethod" value="Email">
  <input type="number" id="login_otp_input" name="Otp">
</form>
"""


class LoginTests(unittest.TestCase):
    def test_mfa_login_exchanges_code_without_storing_password(self) -> None:
        session = FakeSession(
            [
                HttpResponse(
                    "https://identity/connect/authorize", 302, {"Location": "/Account/Login"}, ""
                ),
                HttpResponse("https://identity/Account/Login", 200, {}, LOGIN_HTML),
                HttpResponse(
                    "https://identity/Account/Login", 302, {"Location": "/AccountMfa/VerifyOtp"}, ""
                ),
                HttpResponse("https://identity/AccountMfa/VerifyOtp", 200, {}, MFA_HTML),
                HttpResponse(
                    "https://identity/AccountMfa/VerifyOtp",
                    302,
                    {"Location": "com.myqops://android?code=fresh-code"},
                    "",
                ),
                HttpResponse("https://firebase/appcheck", 200, {}, '{"token":"app-check"}'),
                HttpResponse(
                    "https://identity/connect/token",
                    200,
                    {},
                    '{"access_token":"access","refresh_token":"refresh","expires_in":3600}',
                ),
            ]
        )
        login = MyQLoginSession(session)  # type: ignore[arg-type]

        self.assertIsNone(login.start("driver@example.com", "secret", MFA_METHOD_EMAIL))
        tokens = login.submit_mfa("123456")

        self.assertEqual(tokens.access_token, "access")
        self.assertEqual(tokens.refresh_token, "refresh")
        self.assertGreater(tokens.expires_at, time.time() + 3500)
        login_post = session.calls[2]
        self.assertEqual(login_post.kwargs["data"]["Email"], "driver@example.com")  # type: ignore[index]
        self.assertEqual(login_post.kwargs["data"]["Password"], "secret")  # type: ignore[index]
        token_post = session.calls[-1]
        self.assertEqual(token_post.kwargs["headers"]["Firebase-AppCheck-Token"], "app-check")  # type: ignore[index]

    def test_expired_token_refreshes_and_persists_rotation(self) -> None:
        session = FakeSession(
            [
                HttpResponse(
                    "https://identity/connect/token",
                    200,
                    {},
                    '{"access_token":"new-access","refresh_token":"new-refresh","expires_in":3600}',
                )
            ]
        )
        persisted: list[OAuthTokens] = []
        auth = MyQAuth(
            session,  # type: ignore[arg-type]
            OAuthTokens("expired", "old-refresh", 0),
            persisted.append,
        )

        self.assertEqual(auth.access_token(), "new-access")
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0].refresh_token, "new-refresh")


if __name__ == "__main__":
    unittest.main()
