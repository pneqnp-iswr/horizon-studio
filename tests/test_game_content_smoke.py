"""HS-002 opt-in game content probe: no game assets or executables bundled.

The fake client below only imitates the launch contract read from Horizon's
source; passing these tests is NOT evidence that the real game loads a mod.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.game_content_smoke import (authorized_fixture, assess_content_load, smoke,
                                        verbatim_files)
from horizon_cli import load_project
from studio import hmod_zip

FAKE_CLIENT = textwrap.dedent('''\
    import io, json, os, sys, zipfile
    from pathlib import Path
    args = sys.argv[1:]
    def value(flag):
        return args[args.index(flag) + 1]
    mode = os.environ.get("FAKE_CLIENT_MODE", "load")
    home = Path(value("--home"))
    (home / "logs").mkdir(parents=True)
    log = home / "logs" / "latest.log"
    package = Path(value("--dev-mod"))
    root = Path.cwd() / ".horizon-cache" / "mod-content"
    with zipfile.ZipFile(package) as archive:
        mod_id = archive.read("horizon-mod.toml").decode().split('"')[1]
        if mode == "reject":
            log.write_text(f"[main/WARN]: Horizon: mod {mod_id} content not loaded: bad block\\n")
        else:
            for name in archive.namelist():
                if name.startswith(f"data/{mod_id}/horizon/"):
                    continue
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                data = archive.read(name)
                target.write_bytes(b"{}" if mode == "tamper" and name.endswith(".json") else data)
            log.write_text(f"[main/INFO]: Horizon: content from 1 mod(s) in {root}\\n")
    error = "frame-limited run timed out" if mode == "error" else None
    Path(value("--smoke-report")).write_text(json.dumps({"frames": int(value("--frames")), "error": error}))
    sys.exit(1 if mode == "error" else 0)
''')


class GameContentSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.game = self.root / "fake-horizon"
        self.game.write_bytes(b"test-only fixture; not a runnable game")
        self.project = Path(__file__).resolve().parents[1] / "examples" / "ruby_demo.hstudio.json"
        self.project_data = load_project(self.project)
        self.package = hmod_zip(self.project_data)
        self.expected = verbatim_files(self.package, "ruby_demo")
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
        self.clean = {"frames": 300, "error": None}

    def tearDown(self):
        self.tmp.cleanup()

    def resource_root(self, files=None):
        cache = self.root / ".horizon-cache" / "mod-content"
        for name, content in (self.expected if files is None else files).items():
            target = cache / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return cache

    def test_preflight_rejects_non_matching_artifact(self):
        self.assertTrue(authorized_fixture(self.project_data, self.package, self.data))
        self.data["sha256"] = "0" * 64
        self.assertFalse(authorized_fixture(self.project_data, self.package, self.data))

    def test_verbatim_files_skip_declarations_tags_and_manifest(self):
        workshop = Path(__file__).resolve().parents[1] / "examples" / "workshop_showcase.hstudio.json"
        package = hmod_zip(load_project(workshop))
        names = set(verbatim_files(package, "workshop_showcase"))
        self.assertIn("data/workshop_showcase/recipe/beacon_craft.json", names)
        self.assertIn("data/workshop_showcase/structure/arena.nbt", names)
        self.assertIn("assets/workshop_showcase/lang/en_us.json", names)
        self.assertFalse(any(n.startswith("data/workshop_showcase/horizon/") for n in names))
        self.assertFalse(any("/tags/" in n for n in names))
        self.assertNotIn("horizon-mod.toml", names)

    def test_no_launch_without_explicit_consent(self):
        with patch("scripts.game_content_smoke.subprocess.run") as process:
            with self.assertRaisesRegex(ValueError, "confirm-authorized"):
                smoke(self.game, self.project, self.proof, self.root, timeout=60)
            process.assert_not_called()

    def test_no_launch_without_official_proof(self):
        self.data["ok"] = False
        self.proof.write_text(json.dumps(self.data))
        with patch("scripts.game_content_smoke.subprocess.run") as process:
            with self.assertRaisesRegex(ValueError, "matching successful"):
                smoke(self.game, self.project, self.proof, self.root, timeout=60, confirmed=True)
            process.assert_not_called()

    def test_log_line_without_files_is_indeterminate(self):
        result = assess_content_load("Horizon: content from 1 mod(s) in /tmp/not-existing",
                                     "ruby_demo", self.root, self.expected, 0, False, self.clean)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "indeterminate")

    def test_byte_identical_resource_root_is_content_load_only(self):
        cache = self.resource_root()
        log = f"[12:00:00] [main/INFO]: Horizon: content from 1 mod(s) in {cache}"
        result = assess_content_load(log, "ruby_demo", self.root, self.expected, 0, False, self.clean)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "content_loaded")
        self.assertEqual(result["corroborated_files"], len(self.expected))

    def test_stale_or_foreign_files_do_not_count(self):
        stale = dict(self.expected)
        stale["data/ruby_demo/recipe/ruby_block.json"] = b"{}\n"
        cache = self.resource_root(stale)
        result = assess_content_load(f"Horizon: content from 1 mod(s) in {cache}",
                                     "ruby_demo", self.root, self.expected, 0, False, self.clean)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "indeterminate")
        self.assertIn("data/ruby_demo/recipe/ruby_block.json: different bytes", result["problems"])

    def test_rejected_mod_log_cannot_pass_even_with_files(self):
        cache = self.resource_root()
        result = assess_content_load(
            "Horizon: mod ruby_demo content not loaded: bad manifest\n"
            f"Horizon: content from 1 mod(s) in {cache}",
            "ruby_demo", self.root, self.expected, 0, False, self.clean)
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["ok"])

    def test_missing_or_failed_smoke_report_cannot_pass(self):
        log = f"Horizon: content from 1 mod(s) in {self.resource_root()}"
        missing = assess_content_load(log, "ruby_demo", self.root, self.expected, 0, False, None)
        self.assertEqual(missing["status"], "indeterminate")
        errored = assess_content_load(log, "ruby_demo", self.root, self.expected, 0, False,
                                      {"error": "GPU lost"})
        self.assertEqual(errored["status"], "failed")

    def test_timeout_and_nonzero_exit(self):
        log = "Horizon: content from 1 mod(s) in ."
        self.assertEqual(assess_content_load(log, "ruby_demo", self.root, self.expected,
                                             None, True, None)["status"], "indeterminate")
        failed = assess_content_load(log, "ruby_demo", self.root, self.expected, 101, False,
                                     {"error": "frame-limited run timed out"})
        self.assertEqual(failed["status"], "failed")
        self.assertIn("frame-limited run timed out", failed["reason"])

    def test_script_runs_as_documented(self):
        repo = Path(__file__).resolve().parents[1]
        completed = subprocess.run([sys.executable, str(repo / "scripts" / "game_content_smoke.py"), "--help"],
                                   capture_output=True, text=True, cwd=repo, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--confirm-authorized", completed.stdout)

    @patch("scripts.game_content_smoke.subprocess.run")
    def test_launch_uses_bounded_self_exiting_run(self, process):
        process.return_value = subprocess.CompletedProcess([], 0, "", "")
        result = smoke(self.game, self.project, self.proof, self.root, frames=42, timeout=60,
                       confirmed=True)
        args, kw = process.call_args
        argv = args[0]
        self.assertEqual(argv[1], "--dev-mod")
        for flag, value in (("--frames", "42"), ("--timeout-seconds", "60")):
            self.assertEqual(argv[argv.index(flag) + 1], value)
        self.assertIn("--home", argv)
        self.assertIn("--smoke-report", argv)
        self.assertGreater(kw["timeout"], 60)
        self.assertIs(kw["check"], False)
        self.assertEqual(Path(kw["cwd"]), self.root)
        # The mocked process wrote no report: a clean exit alone is not success.
        self.assertEqual(result["status"], "indeterminate")
        self.assertFalse(result["in_game_behavior_verified"])
        self.assertEqual(result["mod_sha256"], self.hash)


@unittest.skipIf(os.name == "nt", "fake client is a POSIX script")
class FakeClientContractTests(unittest.TestCase):
    """Runs the harness against a real subprocess that imitates the client contract."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.game = self.root / "horizon-client"
        self.game.write_text(f"#!{sys.executable}\n" + FAKE_CLIENT)
        self.game.chmod(0o755)
        self.workdir = self.root / "game"
        self.workdir.mkdir()
        self.project = Path(__file__).resolve().parents[1] / "examples" / "ruby_demo.hstudio.json"
        package = hmod_zip(load_project(self.project))
        digest = hashlib.sha256(package).hexdigest()
        self.proof = self.root / "official.json"
        self.proof.write_text(json.dumps({
            "stage": "official", "ok": True, "exit_code": 0, "sha256": digest, "size": len(package),
            "report": {"ok": True, "report": {"id": "ruby_demo", "kind": "mod", "api": "0.2",
                                              "sha256": digest, "size": len(package)}}}))

    def tearDown(self):
        self.tmp.cleanup()

    def run_mode(self, mode):
        with patch.dict(os.environ, {"FAKE_CLIENT_MODE": mode}):
            return smoke(self.game, self.project, self.proof, self.workdir, frames=5, timeout=30,
                         confirmed=True)

    def test_contract_load(self):
        result = self.run_mode("load")
        self.assertEqual(result["status"], "content_loaded", result["reason"])
        self.assertEqual(result["game_smoke_report"], {"frames": 5, "error": None})
        self.assertFalse(result["gameplay_or_rendering_verified"])

    def test_contract_reject_tamper_and_error(self):
        self.assertEqual(self.run_mode("reject")["status"], "rejected")
        self.assertEqual(self.run_mode("tamper")["status"], "indeterminate")
        self.assertEqual(self.run_mode("error")["status"], "failed")


if __name__ == "__main__":
    unittest.main()
