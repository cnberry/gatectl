from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Mapping

from .errors import MyQApiError


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


@dataclass(frozen=True, slots=True)
class HttpResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: str

    @property
    def location(self) -> str | None:
        return self.headers.get("Location")


class HttpSession:
    """Small cookie-aware HTTP client that leaves redirects to the caller."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.cookies = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            _NoRedirect(),
        )
        self.timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        json_body: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        if params:
            parts = urllib.parse.urlsplit(url)
            query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            query.extend(params.items())
            url = urllib.parse.urlunsplit(
                (
                    parts.scheme,
                    parts.netloc,
                    parts.path,
                    urllib.parse.urlencode(query),
                    parts.fragment,
                )
            )

        body: bytes | None = None
        request_headers = dict(headers or {})
        if data is not None and json_body is not None:
            raise ValueError("Only one request body type may be supplied")
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            # Redirect responses are intentionally surfaced here so OAuth can
            # inspect the custom-scheme callback rather than following it.
            try:
                self.cookies.extract_cookies(error, request)
            except (AttributeError, TypeError):
                pass
            return self._response(error)
        except (urllib.error.URLError, TimeoutError, socket.timeout) as error:
            reason = getattr(error, "reason", error)
            raise MyQApiError(f"Unable to reach MyQ: {reason}") from error
        return self._response(response)

    @staticmethod
    def _response(response) -> HttpResponse:  # type: ignore[no-untyped-def]
        url = response.geturl()
        status = response.status
        headers = response.headers
        try:
            raw = response.read()
        finally:
            response.close()
        charset = headers.get_content_charset() or "utf-8"
        body = raw.decode(charset, errors="replace")
        return HttpResponse(
            url=url,
            status=status,
            headers=headers,
            body=body,
        )
