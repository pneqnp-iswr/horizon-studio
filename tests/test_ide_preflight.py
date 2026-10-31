"""IDE-001 preflight: only real --launch-api replies, zero world starts."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from studio_core.ide_preflight import SCHEMA, report
from studio_core.preview_bridge import BridgeError

ROOT = Path(__file__).resolve().parent.parent
FAKES = ROOT / "tests" / "fakes"


def fake_install(_ctl=None):
    return {
        "ctl": [sys.executable, str(FAKES / "fake_horizon_ctl.py")],
        "game": [sys.executable, str(FAKES / "fake_horizon_client.py")],
    }


class IdePreflightTests(unittest.TestCase):
    def test_good_launch_api_is_compatibility_not_a_game_test(self):
        result = report(locate=fake_install)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["status"], "compatible_for_preview")
        self.assertEqual(result["launch_api"]["launch_api"], "0.1.0")
        self.assertIsNone(result["error"])
        self.assertEqual(result["checks"]["client_discovered"], "passed")
        self.assertEqual(result["checks"]["launch_api_compatible"], "passed")
        self.assertEqual(result["checks"]["game_load"], "not_tested")
        self.assertEqual(result["checks"]["playable_embedded_viewport"], "not_tested")

    def test_wrong_launch_api_does_not_claim_compatibility(self):
        for env in ({"FAKE_LAUNCH_API": "1.0.0"},
                    {"FAKE_LAUNCH_API": "0.0.9"},
                    {"FAKE_LAUNCH_OPTIONS": "--resources,--width"}):
            with self.subTest(env=env), mock.patch.dict(os.environ, env):
                data = report(locate=fake_install)
                self.assertEqual(data["status"], "blocked")
                self.assertEqual(data["error"]["code"], "VERSION_UNSUPPORTED")
                self.assertEqual(data["checks"]["launch_api_compatible"], "failed")
                self.assertEqual(data["checks"]["game_load"], "not_tested")

    def test_explicit_nonexistent_ctl_never_falls_back_to_path(self):
        def forbidden(_ctl):
            self.fail("Explicit invalid path was ignored")
        result = report("/missing/horizon-ctl", locate=forbidden)
        self.assertEqual(result["error"]["code"], "NOT_FOUND")
        self.assertIsNone(result["installation"])

    def test_missing_client_is_blocked_before_running_anything(self):
        found = lambda _ctl: {"ctl": ["/safe/horizon-ctl"], "game": None}
        data = report(locate=found)
        self.assertEqual(data["error"]["code"], "VERSION_UNKNOWN")
        self.assertEqual(data["checks"]["client_discovered"], "failed")
        self.assertEqual(data["status"], "blocked")

    def test_discovery_refusal_is_machine_readable(self):
        def unavailable(_ctl):
            raise BridgeError("NOT_FOUND", "The game was not installed")
        data = report(locate=unavailable)
        self.assertEqual(data["error"], {"code": "NOT_FOUND", "message": "The game was not installed"})
        self.assertEqual(data["checks"]["client_discovered"], "failed")
        self.assertIsNone(data["launch_api"])


if __name__ == "__main__":
    unittest.main()
