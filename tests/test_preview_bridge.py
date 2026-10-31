"""HS-023: the Preview Bridge against stand-ins for horizon-ctl and horizon-client (no real game here)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from studio_core.migrate import to_generator_request, upgrade
from studio_core.preview_bridge import BridgeError, PreviewBridge, discover

ROOT = Path(__file__).resolve().parent.parent
FAKES = ROOT / "tests" / "fakes"
CTL = [sys.executable, str(FAKES / "fake_horizon_ctl.py")]
GAME = [sys.executable, str(FAKES / "fake_horizon_client.py")]


def ruby_package(folder: Path) -> Path:
    from studio import hmod_zip
    doc = upgrade(json.loads((ROOT / "examples" / "ruby_demo.hstudio.json").read_text(encoding="utf-8")))
    path = folder / "ruby_demo.hmod"
    path.write_bytes(hmod_zip(to_generator_request(doc)))
    return path


class PreviewBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.hmod = ruby_package(self.folder)
        # A personal world that must never be touched.
        self.personal = self.folder / "personal-saves" / "My World"
        self.personal.mkdir(parents=True)
        (self.personal / "level.dat").write_bytes(b"mine")
        self.bridge = PreviewBridge(CTL, GAME, self.folder / "preview")

    def tearDown(self):
        self.bridge.end()
        self.tmp.cleanup()

    def test_a_full_session_in_an_isolated_world_reaches_game_load_only_when_the_game_confirms_the_items(self):
        self.assertEqual(self.bridge.check_version()["launch_api"], "0.1.0")
        session = self.bridge.start(self.hmod, approved=True, seed=5)
        game_dir = Path(session["game_dir"])
        self.assertTrue(game_dir.is_relative_to(self.folder / "preview"))
        self.assertTrue((game_dir / "saves" / "StudioPreview" / "level.dat").is_file(), "a fresh test world")
        self.assertEqual((self.personal / "level.dat").read_bytes(), b"mine")
        shot = self.bridge.screenshot(self.folder / "view.png")
        self.assertEqual(len(shot["sha256"]), 64)
        state = self.bridge.state()
        content = self.bridge.verify_items(["ruby_demo:ruby"])
        self.assertTrue(content["all_found"])
        # The package goes in as a dev mod, offscreen, with the isolated folders.
        args = json.loads(Path(session["socket"] + ".state").read_text())["args"]
        self.assertEqual(args[args.index("--dev-mod") + 1], str(self.hmod))
        self.assertEqual(args[args.index("--game-dir") + 1], session["game_dir"])
        self.assertIn("--offscreen", args)
        self.assertEqual(self.bridge.end()["how"], "quit")
        evidence = self.bridge.evidence(screenshot=shot, state=state, content=content)
        self.assertEqual(evidence["schema"], "horizon-studio.preview-evidence/1")
        self.assertEqual(evidence["level"], "game-load")
        self.assertEqual(evidence["package"]["sha256"], session["hmod_sha256"])
        self.assertTrue(any("not, by itself, proof" in note for note in evidence["notes"]))
        commands = [entry["command"] for entry in evidence["commands"]]
        self.assertEqual(commands[:2], ["launch", "wait-for"])
        self.assertEqual(commands[-1], "quit")

    def test_a_screenshot_alone_is_not_game_load(self):
        self.bridge.start(self.hmod, approved=True)
        shot = self.bridge.screenshot(self.folder / "view.png")
        content = self.bridge.verify_items(["ruby_demo:not_in_the_package"])
        self.assertFalse(content["all_found"])
        self.bridge.end()
        evidence = self.bridge.evidence(screenshot=shot, state=None, content=content)
        self.assertEqual(evidence["level"], "launched")
        self.assertEqual(self.bridge.evidence(screenshot=shot, state=None, content=None)["level"], "launched")

    def test_nothing_starts_without_approval_a_checked_version_or_a_package(self):
        with self.assertRaises(BridgeError) as refused:
            self.bridge.start(self.hmod, approved=False)
        self.assertEqual(refused.exception.code, "APPROVAL_REQUIRED")
        with self.assertRaises(BridgeError) as bad:
            self.bridge.start(self.folder / "missing.hmod", approved=True)
        self.assertEqual(bad.exception.code, "BAD_PACKAGE")
        blind = PreviewBridge(CTL, None, self.folder / "preview")
        with self.assertRaises(BridgeError) as unknown:
            blind.start(self.hmod, approved=True)
        self.assertEqual(unknown.exception.code, "VERSION_UNKNOWN")
        for env, why in (({"FAKE_LAUNCH_API": "1.0.0"}, "major"), ({"FAKE_LAUNCH_API": "0.0.9"}, "too old"),
                         ({"FAKE_LAUNCH_API": "soon"}, "not a version"), ({"FAKE_LAUNCH_OPTIONS": "--resources,--width"}, "options")):
            with self.subTest(why), mock.patch.dict(os.environ, env):
                with self.assertRaises(BridgeError) as unsupported:
                    PreviewBridge(CTL, GAME, self.folder / "preview").check_version()
                self.assertEqual(unsupported.exception.code, "VERSION_UNSUPPORTED")
        self.assertFalse((self.folder / "preview").exists(), "no session folder was created")

    def test_failures_are_reported_and_the_session_still_ends(self):
        with mock.patch.dict(os.environ, {"FAKE_CTL_MODE": "unreachable"}):
            with self.assertRaises(BridgeError) as unreachable:
                self.bridge.start(self.hmod, approved=True)
        self.assertEqual(unreachable.exception.code, "UNREACHABLE")
        self.assertTrue(self.bridge.session["ended"])
        bridge = PreviewBridge(CTL, GAME, self.folder / "preview")
        bridge.start(self.hmod, approved=True)
        with mock.patch.dict(os.environ, {"FAKE_CTL_MODE": "no-png"}):
            with self.assertRaises(BridgeError) as fake:
                bridge.screenshot(self.folder / "fake.png")
        self.assertEqual(fake.exception.code, "BAD_SCREENSHOT")
        with mock.patch.dict(os.environ, {"FAKE_CTL_MODE": "quit-hangs"}), mock.patch("os.kill") as kill:
            ended = bridge.end()
        self.assertIn("quit failed", ended["how"])
        kill.assert_called_once()
        self.assertEqual(bridge.end(), {"ended": True}, "ending twice is harmless")

    def test_discovery_finds_horizon_ctl_and_the_game_beside_it(self):
        with self.assertRaises(BridgeError) as missing:
            discover(None, environ={})
        self.assertEqual(missing.exception.code, "NOT_FOUND")
        install = self.folder / "horizon"
        install.mkdir()
        ctl = install / ("horizon-ctl.exe" if sys.platform == "win32" else "horizon-ctl")
        ctl.write_bytes(b"")
        found = discover(None, environ={"HORIZON_CTL": str(ctl)})
        self.assertEqual(found["ctl"], [str(ctl.resolve())])
        self.assertIsNone(found["game"], "no horizon-client beside it: the version cannot be checked")
        (install / ("horizon-client.exe" if sys.platform == "win32" else "horizon-client")).write_bytes(b"")
        self.assertIsNotNone(discover(str(ctl), environ={})["game"])


if __name__ == "__main__":
    unittest.main()


class PreviewCliTests(unittest.TestCase):
    def test_the_cli_needs_approval_and_writes_evidence(self):
        import contextlib
        import io
        from horizon_cli import main
        from studio_core.preview_bridge import CLIENT, CTL as CTL_NAME
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            install = folder / "horizon"
            install.mkdir()
            # Executable stand-ins with the real names, so discovery works as it would on a real install.
            for name, script in ((CTL_NAME, "fake_horizon_ctl.py"), (CLIENT, "fake_horizon_client.py")):
                if sys.platform == "win32":
                    self.skipTest("the CLI stand-ins are shell scripts")
                target = install / name
                target.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKES / script} \"$@\"\n")
                target.chmod(0o755)
            project = ROOT / "examples" / "ruby_demo.hstudio.json"
            out = folder / "evidence.json"
            err = io.StringIO()
            with mock.patch.dict(os.environ, {"HOME": str(folder)}), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(err):
                self.assertEqual(main(["preview", str(project), "--ctl", str(install / CTL_NAME), "-o", str(out)]), 1)
            self.assertIn("APPROVAL_REQUIRED", err.getvalue())
            self.assertFalse(out.exists())
            with mock.patch.dict(os.environ, {"HOME": str(folder)}), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["preview", str(project), "--ctl", str(install / CTL_NAME), "--yes",
                                       "--item", "ruby_demo:ruby", "-o", str(out)]), 0)
            evidence = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(evidence["level"], "game-load")
            self.assertTrue(out.with_suffix(".png").is_file())
            self.assertTrue(evidence["session"]["game_dir"].startswith(str(folder / ".horizon-studio" / "preview")))
