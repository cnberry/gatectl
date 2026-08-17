from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gatectl.models import OAuthTokens
from gatectl.storage import (
    CONFIG_ROOT,
    load_tokens,
    save_tokens,
    target_config_path,
    token_path,
)


class StorageTests(unittest.TestCase):
    def test_system_config_paths_are_the_defaults(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(target_config_path(), CONFIG_ROOT / "targets.json")
            self.assertEqual(token_path(), CONFIG_ROOT / "tokens.json")

    def test_tokens_round_trip_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "tokens.json"
            expected = OAuthTokens("access", "refresh", 12345.0)

            save_tokens(expected, path)

            self.assertEqual(load_tokens(path), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
