from __future__ import annotations

import unittest

from gatectl.cli import load_target_config, select_targets
from gatectl.models import MyQDevice


class TargetTests(unittest.TestCase):
    def test_selects_names_case_insensitively(self) -> None:
        devices = (
            MyQDevice(
                "a", "Demo Home", "1", "Driveway Gate", "garagedoor", None, {"door_state": "closed"}
            ),
            MyQDevice(
                "a", "Demo Home", "2", "Garage Door", "garagedoor", None, {"door_state": "open"}
            ),
            MyQDevice("a", "Demo Home", "3", "Main Hub", "gateway", None, {}),
        )

        matches = select_targets(devices, ("driveway gate", "GARAGE DOOR"))

        self.assertEqual([device.name for device in matches], ["Driveway Gate", "Garage Door"])

    def test_restricts_matches_to_configured_account(self) -> None:
        devices = (
            MyQDevice(
                "a", "Other Home", "1", "Garage Door", "garagedoor", None, {"door_state": "open"}
            ),
            MyQDevice(
                "b", "Demo Home", "2", "Garage Door", "garagedoor", None, {"door_state": "closed"}
            ),
        )

        matches = select_targets(devices, ("Garage Door",), account_name="demo home")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].account_id, "b")
        self.assertEqual(matches[0].door_state, "closed")

    def test_loads_account_and_names_together(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.json"
            path.write_text(
                '{"account":"Demo Home","devices":["Garage Door"]}',
                encoding="utf-8",
            )

            self.assertEqual(load_target_config(path), ("Demo Home", ("Garage Door",)))

    def test_rejects_missing_or_ambiguous_target_config(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.json"
            with self.assertRaisesRegex(ValueError, "No target config"):
                load_target_config(path)

            path.write_text(
                '{"account":"Demo Home","devices":["Garage Door","garage door"]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate device"):
                load_target_config(path)


if __name__ == "__main__":
    unittest.main()
