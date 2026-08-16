from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path

from gatectl.models import OAuthTokens
from gatectl.storage import load_tokens, save_tokens


class StorageTests(unittest.TestCase):
    def test_tokens_round_trip_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "tokens.json"
            expected = OAuthTokens("access", "refresh", 12345.0)

            save_tokens(expected, path)

            self.assertEqual(load_tokens(path), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
