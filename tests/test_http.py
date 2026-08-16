from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from gatectl.http import HttpSession


class _CookieRedirectHandler(BaseHTTPRequestHandler):
    seen_cookie: str | None = None

    def do_GET(self) -> None:
        if self.path == "/start":
            self.send_response(302)
            self.send_header("Location", "/next")
            self.send_header("Set-Cookie", "session=test-value; Path=/")
            self.end_headers()
            return
        type(self).seen_cookie = self.headers.get("Cookie")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:
        return


class HttpSessionTests(unittest.TestCase):
    def test_preserves_cookie_from_surfaced_redirect(self) -> None:
        _CookieRedirectHandler.seen_cookie = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), _CookieRedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            session = HttpSession(timeout=2)

            redirect = session.request("GET", f"{base_url}/start")
            result = session.request("GET", f"{base_url}/next")

            self.assertEqual(redirect.status, 302)
            self.assertEqual(redirect.location, "/next")
            self.assertEqual(result.status, 200)
            self.assertEqual(_CookieRedirectHandler.seen_cookie, "session=test-value")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
