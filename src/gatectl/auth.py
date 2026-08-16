"""MyQ residential OAuth login, MFA, token exchange, and refresh.

This is a dependency-free adaptation of the form-driven OAuth flow in
https://github.com/bvdcode/myq-home-assistant (MIT, Copyright 2026 Vadim
Belov). It intentionally contains no device command code.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, Mapping

from .constants import (
    ANDROID_CERT_SHA1,
    ANDROID_PACKAGE,
    APP_VERSION,
    BRAND_ID,
    FIREBASE_API_KEY,
    FIREBASE_APP_ID,
    FIREBASE_DEBUG_TOKEN,
    FIREBASE_PROJECT_ID,
    IDENTITY_BASE_URL,
    MFA_METHOD_EMAIL,
    MFA_METHOD_SMS,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPE,
    TOKEN_EXPIRY_MARGIN,
    USER_AGENT,
)
from .errors import (
    MyQApiError,
    MyQAuthenticationError,
    MyQCloudflareChallengeError,
    MyQInvalidCredentialsError,
    MyQInvalidMfaError,
)
from .http import HttpResponse, HttpSession
from .models import OAuthTokens

TokenListener = Callable[[OAuthTokens], None]


@dataclass(frozen=True, slots=True)
class ParsedForm:
    action: str
    fields: dict[str, str]
    email_field: str | None
    password_field: str | None
    otp_field: str | None


@dataclass(frozen=True, slots=True)
class MfaForm:
    page_url: str
    action: str
    fields: dict[str, str]
    otp_field: str


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[ParsedForm] = []
        self._action: str | None = None
        self._fields: dict[str, str] = {}
        self._email_field: str | None = None
        self._password_field: str | None = None
        self._otp_field: str | None = None
        self._visible_fields: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value for name, value in attrs}
        if tag.casefold() == "form":
            self._finish_form()
            self._action = attributes.get("action") or ""
            return
        if tag.casefold() != "input" or self._action is None:
            return
        if "disabled" in attributes:
            return
        name = attributes.get("name")
        if not name:
            return
        field_type = (attributes.get("type") or "text").casefold()
        if field_type in {"button", "image", "reset", "submit"}:
            return
        self._fields[name] = attributes.get("value") or ""
        identity = " ".join(
            (name, attributes.get("id") or "", attributes.get("autocomplete") or "")
        ).casefold()
        if field_type == "email" or "email" in identity:
            self._email_field = name
        if field_type == "password":
            self._password_field = name
        if (
            "otp" in identity
            or "one-time-code" in identity
            or re.search(r"(^|\W)(verification|security)[_-]?code($|\W)", identity)
        ):
            self._otp_field = name
        if field_type in {"number", "tel", "text"}:
            self._visible_fields.append(name)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "form":
            self._finish_form()

    def close(self) -> None:
        super().close()
        self._finish_form()

    def _finish_form(self) -> None:
        if self._action is None:
            return
        otp_field = self._otp_field
        if otp_field is None and "verifyotp" in self._action.casefold():
            otp_field = next(
                (
                    name
                    for name in self._fields
                    if "otp" in name.casefold() or name.casefold().endswith("code")
                ),
                self._visible_fields[0] if len(self._visible_fields) == 1 else None,
            )
        self.forms.append(
            ParsedForm(
                self._action,
                dict(self._fields),
                self._email_field,
                self._password_field,
                otp_field,
            )
        )
        self._action = None
        self._fields = {}
        self._email_field = None
        self._password_field = None
        self._otp_field = None
        self._visible_fields = []


class MyQAuth:
    def __init__(
        self,
        session: HttpSession,
        tokens: OAuthTokens,
        token_listener: TokenListener,
    ) -> None:
        self._session = session
        self._tokens = tokens
        self._token_listener = token_listener

    def access_token(self) -> str:
        margin = TOKEN_EXPIRY_MARGIN.total_seconds()
        if self._tokens.expires_at - margin <= time.time():
            self.refresh()
        return self._tokens.access_token

    def refresh(self) -> OAuthTokens:
        payload = _post_json(
            self._session,
            f"{IDENTITY_BASE_URL}/connect/token",
            data={
                "client_id": OAUTH_CLIENT_ID,
                "scope": OAUTH_SCOPE,
                "redirect_uri": OAUTH_REDIRECT_URI,
                "grant_type": "refresh_token",
                "refresh_token": self._tokens.refresh_token,
            },
            headers=_token_headers(),
        )
        self._tokens = _oauth_tokens(payload, self._tokens.refresh_token)
        self._token_listener(self._tokens)
        return self._tokens


class MyQLoginSession:
    def __init__(self, session: HttpSession) -> None:
        self._session = session
        self._verifier: str | None = None
        self._mfa_form: MfaForm | None = None

    def probe(self) -> dict[str, object]:
        authorization_url, _ = _authorization_url()
        page = self._request_page("GET", authorization_url, headers=_login_headers())
        code, page = self._follow_redirects(page)
        if code is not None:
            raise MyQApiError("MyQ unexpectedly authorized an anonymous probe")
        _raise_for_challenge(page.body)
        form = _login_form(page)
        return {
            "reachable": True,
            "http_status": page.status,
            "path": urllib.parse.urlsplit(page.url).path,
            "login_form": True,
            "email_field": form.email_field,
            "password_field": form.password_field,
        }

    def start(
        self,
        email_address: str,
        password: str,
        mfa_method: str,
    ) -> OAuthTokens | None:
        authorization_url, verifier = _authorization_url()
        self._verifier = verifier
        page = self._request_page("GET", authorization_url, headers=_login_headers())
        authorization_code, page = self._follow_redirects(page)
        if authorization_code is not None:
            return self._exchange_code(authorization_code)
        _raise_for_challenge(page.body)

        form = _login_form(page)
        fields = dict(form.fields)
        if form.email_field is None or form.password_field is None:
            raise MyQApiError("The MyQ sign-in form is incomplete")
        fields[form.email_field] = email_address
        fields[form.password_field] = password
        submitted = self._request_page(
            "POST",
            urllib.parse.urljoin(page.url, form.action),
            data=fields,
            headers=_login_headers(referer=page.url, form_post=True),
        )
        authorization_code, result = self._follow_redirects(submitted)
        if authorization_code is not None:
            return self._exchange_code(authorization_code)
        _raise_for_challenge(result.body)

        message = _validation_error(result.body)
        if message is not None:
            raise MyQInvalidCredentialsError(message)
        authorization_code, result = self._select_mfa_method(result, mfa_method)
        if authorization_code is not None:
            return self._exchange_code(authorization_code)
        _raise_for_challenge(result.body)
        self._set_mfa_form(result)
        return None

    def submit_mfa(self, code: str) -> OAuthTokens:
        if self._mfa_form is None:
            raise MyQApiError("No active MyQ verification challenge")
        fields = dict(self._mfa_form.fields)
        fields[self._mfa_form.otp_field] = code
        submitted = self._request_page(
            "POST",
            self._mfa_form.action,
            data=fields,
            headers=_login_headers(referer=self._mfa_form.page_url, form_post=True),
        )
        authorization_code, result = self._follow_redirects(submitted)
        authorization_code, result = self._follow_consent(authorization_code, result)
        if authorization_code is None:
            message = _validation_error(result.body)
            try:
                self._set_mfa_form(result)
            except MyQApiError:
                pass
            raise MyQInvalidMfaError(message or "MyQ rejected the verification code")
        return self._exchange_code(authorization_code)

    def _exchange_code(self, code: str) -> OAuthTokens:
        if self._verifier is None:
            raise MyQApiError("The PKCE verifier is missing")
        app_check_token = _mint_app_check_token(self._session)
        payload = _post_json(
            self._session,
            f"{IDENTITY_BASE_URL}/connect/token",
            data={
                "client_id": OAUTH_CLIENT_ID,
                "scope": OAUTH_SCOPE,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OAUTH_REDIRECT_URI,
                "code_verifier": self._verifier,
            },
            headers={**_token_headers(), "Firebase-AppCheck-Token": app_check_token},
        )
        return _oauth_tokens(payload)

    def _follow_redirects(self, page: HttpResponse) -> tuple[str | None, HttpResponse]:
        current = page
        for _ in range(12):
            if current.location is None:
                return None, current
            target = urllib.parse.urljoin(current.url, current.location)
            if target.startswith(OAUTH_REDIRECT_URI):
                return _redirect_code(target), current
            current = self._request_page("GET", target, headers=_login_headers())
        raise MyQApiError("Too many redirects while completing MyQ sign-in")

    def _select_mfa_method(
        self,
        page: HttpResponse,
        mfa_method: str,
    ) -> tuple[str | None, HttpResponse]:
        server_method = {MFA_METHOD_EMAIL: "Email", MFA_METHOD_SMS: "Sms"}.get(mfa_method)
        if server_method is None:
            raise MyQApiError("Unsupported MyQ verification method")
        form = _otp_form(page.body)
        selected_method = next(
            (
                value
                for name, value in form.fields.items()
                if name.casefold() == "selectedmfamethod"
            ),
            None,
        )
        if selected_method and selected_method.casefold() == server_method.casefold():
            return None, page
        split_url = urllib.parse.urlsplit(page.url)
        query = [
            (name, value)
            for name, value in urllib.parse.parse_qsl(split_url.query, keep_blank_values=True)
            if name.casefold() != "selectedmfamethod"
        ]
        query.append(("selectedMfaMethod", server_method))
        switch_url = urllib.parse.urlunsplit(
            (
                split_url.scheme,
                split_url.netloc,
                split_url.path,
                urllib.parse.urlencode(query),
                split_url.fragment,
            )
        )
        switched = self._request_page("GET", switch_url, headers=_login_headers(referer=page.url))
        return self._follow_redirects(switched)

    def _follow_consent(
        self,
        authorization_code: str | None,
        page: HttpResponse,
    ) -> tuple[str | None, HttpResponse]:
        if authorization_code is not None:
            return authorization_code, page
        if urllib.parse.urlsplit(page.url).path.casefold() != "/consent":
            return None, page
        form = _consent_form(page.body)
        post_url = urllib.parse.urljoin(page.url, form.action)
        consented = self._request_page(
            "POST",
            post_url,
            data=form.fields,
            headers=_login_headers(referer=page.url, form_post=True),
        )
        if consented.status == 200:
            return_url = urllib.parse.parse_qs(urllib.parse.urlsplit(post_url).query).get(
                "returnUrl", [""]
            )[0]
            resumed_url = urllib.parse.urljoin(IDENTITY_BASE_URL, return_url)
            resumed = urllib.parse.urlsplit(resumed_url)
            identity = urllib.parse.urlsplit(IDENTITY_BASE_URL)
            if (
                resumed.scheme == identity.scheme
                and resumed.netloc == identity.netloc
                and resumed.path == "/connect/authorize/callback"
            ):
                consented = self._request_page(
                    "GET", resumed_url, headers=_login_headers(referer=page.url)
                )
        return self._follow_redirects(consented)

    def _request_page(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        return self._session.request(method, url, data=data, headers=headers)

    def _set_mfa_form(self, page: HttpResponse) -> None:
        form = _otp_form(page.body)
        if form.otp_field is None:
            raise MyQApiError("The MyQ verification form has no code field")
        self._mfa_form = MfaForm(
            page_url=page.url,
            action=urllib.parse.urljoin(page.url, form.action),
            fields=form.fields,
            otp_field=form.otp_field,
        )


def _mint_app_check_token(session: HttpSession) -> str:
    endpoint = (
        "https://firebaseappcheck.googleapis.com/v1/projects/"
        f"{FIREBASE_PROJECT_ID}/apps/{FIREBASE_APP_ID}:exchangeDebugToken"
    )
    payload = _post_json(
        session,
        endpoint,
        params={"key": FIREBASE_API_KEY},
        json_body={"debugToken": FIREBASE_DEBUG_TOKEN},
        headers={"X-Android-Package": ANDROID_PACKAGE, "X-Android-Cert": ANDROID_CERT_SHA1},
    )
    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise MyQApiError("Firebase App Check did not return a token")
    return token


def _post_json(
    session: HttpSession,
    url: str,
    *,
    data: Mapping[str, str] | None = None,
    params: Mapping[str, str] | None = None,
    json_body: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
) -> dict[str, object]:
    response = session.request(
        "POST",
        url,
        data=data,
        params=params,
        json_body=json_body,
        headers=headers,
    )
    try:
        parsed = json.loads(response.body)
    except json.JSONDecodeError as error:
        raise MyQApiError(
            f"MyQ returned HTTP {response.status} with an invalid JSON body"
        ) from error
    if not isinstance(parsed, dict):
        raise MyQApiError("MyQ returned an unexpected JSON response")
    if response.status < 400:
        return parsed
    error_code = parsed.get("code") or parsed.get("error")
    if response.status in {400, 401, 403}:
        raise MyQAuthenticationError(str(error_code or response.status))
    raise MyQApiError(f"MyQ request failed with HTTP {response.status}")


def _oauth_tokens(
    payload: Mapping[str, object],
    existing_refresh_token: str | None = None,
) -> OAuthTokens:
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token", existing_refresh_token)
    expires_in = payload.get("expires_in")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        raise MyQApiError("MyQ returned an incomplete OAuth token response")
    if not isinstance(expires_in, int | float):
        raise MyQApiError("MyQ returned an invalid OAuth expiry")
    return OAuthTokens(access_token, refresh_token, time.time() + float(expires_in))


def _authorization_url() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    query = urllib.parse.urlencode(
        {
            "acr_values": "unified_flow:v1 brand:myq",
            "client_id": OAUTH_CLIENT_ID,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "ui_locales": "en-US",
            "redirect_uri": OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": OAUTH_SCOPE,
            "prompt": "login",
        }
    )
    return f"{IDENTITY_BASE_URL}/connect/authorize?{query}", verifier


def _token_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "App-Version": APP_VERSION,
        "BrandId": BRAND_ID,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    }


def _login_headers(*, referer: str | None = None, form_post: bool = False) -> dict[str, str]:
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 11; sdk_gphone_x86) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/83.0.4103.106 Mobile Safari/537.36"
        ),
        "Upgrade-Insecure-Requests": "1",
    }
    if referer is not None:
        headers["Referer"] = referer
    if form_post:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Origin"] = IDENTITY_BASE_URL
    return headers


def _parse_forms(page_html: str) -> list[ParsedForm]:
    parser = _FormParser()
    parser.feed(page_html)
    parser.close()
    return parser.forms


def _login_form(page: HttpResponse) -> ParsedForm:
    form = next(
        (candidate for candidate in _parse_forms(page.body) if candidate.password_field), None
    )
    if form is None or form.email_field is None or not form.action:
        raise MyQApiError(f"The MyQ sign-in form was not found ({_page_summary(page)})")
    return form


def _otp_form(page_html: str) -> ParsedForm:
    form = next((candidate for candidate in _parse_forms(page_html) if candidate.otp_field), None)
    if form is None or form.otp_field is None or not form.action:
        raise MyQApiError("The MyQ verification form was not recognized")
    return form


def _consent_form(page_html: str) -> ParsedForm:
    form = next(
        (
            candidate
            for candidate in _parse_forms(page_html)
            if "consent" in candidate.action.casefold()
        ),
        None,
    )
    if form is None or not form.action:
        raise MyQApiError("The MyQ consent form was not recognized")
    return ParsedForm(form.action, {**form.fields, "button": "yes"}, None, None, None)


def _validation_error(page_html: str) -> str | None:
    flattened = re.sub(r"\s+", " ", page_html)
    match = re.search(
        r"validation-summary-errors.*?<ul>(.*?)</ul>|field-validation-error[^>]*>(.*?)<",
        flattened,
        re.IGNORECASE,
    )
    if match is None:
        return None
    raw = match.group(1) or match.group(2) or ""
    message = html.unescape(re.sub(r"<[^>]+>", " ", raw)).strip()
    return re.sub(r"\s+", " ", message) or None


def _raise_for_challenge(page_html: str) -> None:
    if any(marker in page_html for marker in ("Just a moment", "Verify you are human")):
        raise MyQCloudflareChallengeError("MyQ returned a browser verification challenge")


def _redirect_code(redirect_url: str) -> str:
    code = urllib.parse.parse_qs(urllib.parse.urlsplit(redirect_url).query).get("code", [""])[0]
    if not code:
        raise MyQApiError("The MyQ callback did not contain an authorization code")
    return code


def _page_summary(page: HttpResponse) -> str:
    path = urllib.parse.urlsplit(page.url).path or "/"
    title_match = re.search(r"<title\b[^>]*>(.*?)</title>", page.body, re.I | re.S)
    title = _plain_text(title_match.group(1)) if title_match else ""
    parts = [f"HTTP {page.status} at {path}"]
    if title:
        parts.append(f"title={title[:120]!r}")
    return ", ".join(parts)


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()
