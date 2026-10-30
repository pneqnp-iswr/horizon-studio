"""HS-002 opt-in game content probe: no game assets or executables bundled."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.game_content_smoke import authorized_fixture, assess_content_load, smoke
from horizon_cli import load_project
from studio import hmod_zip


class GameContentSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.game = self.root / "fake-horizon"
        self.game.write_bytes(b"test-only fixture; not a runnable game")
        self.project = Path(__file__).resolve().parents[1] / "examples" / "ruby_demo.hstudio.json"
        self.project_data = load_project(self.project)
        self.package = hmod_zip(self.project_data)
        self.hash = hashlib.sha256(self.package).hexdigest()
        self.proof = self.root / "official.json"
        self.data = {
            "stage": "official", "ok": True, "exit_code": 0,
            "sha256": self.hash, "size": len(self.package),
            "report": {"ok": True, "report": {
                "id": "ruby_demo", "kind": "mod", "api": "0.2",
                "sha256": self.hash, "size": len(self.package)}},
        }
        self.proof.write_text(json.dumps(self.data))
        self.log = self.root / "latest.log"

    def tearDown(self):
        self.tmp.cleanup()

    def test_preflight_rejects_non_matching_artifact(self):
        self.assertTrue(authorized_fixture(self.project_data, self.package, self.data))
        self.data["sha256"] = "0" * 64
        self.assertFalse(authorized_fixture(self.project_data, self.package, self.data))

    def test_no_launch_without_explicit_consent(self):
        with patch("scripts.game_content_smoke.subprocess.run") as process:
            with self.assertRaisesRegex(ValueError, "confirm-authorized"):
                smoke(self.game, self.project, self.proof, self.root, self.log, 60, False)
            process.assert_not_called()

    def test_no_launch_without_official_proof(self):
        self.data["ok"] = False
        self.proof.write_text(json.dumps(self.data))
        with patch("scripts.game_content_smoke.subprocess.run") as process:
            with self.assertRaisesRegex(ValueError, "matching successful"):
                smoke(self.game, self.project, self.proof, self.root, self.log, 60, True)
            process.assert_not_called()

    def test_ambiguous_log_does_not_count_as_success(self):
        result = assess_content_load("Horizon: content from 1 mod(s) in /tmp/not-existing",
                                     "ruby_demo", self.root, 0, False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "indeterminate")

    def test_correlated_cache_and_real_log_produces_content_load_only(self):
        cache = self.root / ".cache"
        target = cache / "data" / "ruby_demo" / "horizon" / "item"
        target.mkdir(parents=True)
        (target / "ruby.json").write_text("{}")
        log = f"Horizon: content from 1 mod(s) in {cache}"
        result = assess_content_load(log, "ruby_demo", self.root, 0, False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "content_loaded")

    def test_rejected_mod_log_cannot_pass_even_with_cache(self):
        cache = self.root / ".cache" / "data" / "ruby_demo"
        cache.mkdir(parents=True)
        (cache / "test.json").write_text("{}")
        result = assess_content_load(
            f"Horizon: mod ruby_demo content not loaded: bad manifest\n"
            f"Horizon: content from 1 mod(s) in {self.root / '.cache'}",
            "ruby_demo", self.root, 0, False)
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["ok"])

    @patch("scripts.game_content_smoke.subprocess.run")
    def test_launch_records_narrow_evidence_not_gameplay(self, process):
        cache = self.root / ".cache" / "data" / "ruby_demo"
        cache.mkdir(parents=True)
        (cache / "fixture.json").write_text("{}")
        process.return_value = subprocess.CompletedProcess(
            [], 0, f"Horizon: content from 1 mod(s) in {self.root / '.cache'}", "")
        result = smoke(self.game, self.project, self.proof, self.root, self.log, 60, True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["in_game_behavior_verified"])
        self.assertFalse(result["gameplay_or_rendering_verified"])
        args, kw = process.call_args
        self.assertEqual(args[0][1], "--dev-mod")
        self.assertTrue(kw["check"] is False)
        self.assertEqual(result["mod_sha256"], self.hash)

    def test_timeout_is_indeterminate(self):
        self.assertEqual(assess_content_load("Horizon: content from 1 mod(s) in .",
                                              "ruby_demo", self.root, None, True)["status"],
                         "indeterminate")


if __name__ == "__main__":
    unittest.main()
