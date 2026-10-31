"""HS-023: the Preview Bridge against stand-ins for horizon-ctl and horizon-client (no real game here)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from studio_core.migrate import to_generator_request, upgrade
from studio_core.preview_bridge import BridgeError, PreviewBridge, discover, package_items, parse_inventory

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
        self.bridge = PreviewBridge(CTL, GAME, self.folder / "preview", sleep=lambda _s: None)

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
        self.assertTrue(Path(shot["path"]).is_relative_to(Path(session["folder"])), "the game writes only inside the session")
        self.assertEqual((self.folder / "view.png").read_bytes(), Path(shot["path"]).read_bytes())
        state = self.bridge.state()
        content = self.bridge.verify_items(["ruby_demo:ruby"])
        self.assertTrue(content["all_found"])
        [check] = content["checks"]
        self.assertEqual((check["before"], check["after"], check["slots"]), (0, 1, [0]))
        self.assertTrue(content["control"]["refused"], "the same game refused an item the package does not define")
        # The package goes in as a dev mod, offscreen, with the isolated folders.
        args = json.loads(Path(session["socket"] + ".state").read_text())["args"]
        self.assertEqual(args[args.index("--dev-mod") + 1], str(self.hmod))
        self.assertEqual(args[args.index("--game-dir") + 1], session["game_dir"])
        self.assertIn("--offscreen", args)
        self.assertEqual(self.bridge.end()["how"], "quit")
        evidence = self.bridge.evidence(screenshot=shot, state=state, content=content)
        self.assertEqual(evidence["schema"], "horizon-studio.preview-evidence/1")
        self.assertEqual(evidence["level"], "game-load")
        self.assertEqual(evidence["binding"], {"package_sha256": session["hmod_sha256"], "horizon_version": "v2026.10.31",
                                               "launch_api": "0.1.0", "session": session["id"], "world": "StudioPreview",
                                               "seed": 5})
        self.assertEqual(len(evidence["digest"]), 64)
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
        with mock.patch.dict(os.environ, {"FAKE_CTL_MODE": "quit-hangs"}), mock.patch("os.kill") as kill, \
                mock.patch.object(PreviewBridge, "command_line", return_value=f"horizon-client --game-dir {bridge.session['game_dir']}"):
            ended = bridge.end()
        self.assertIn("quit failed", ended["how"])
        kill.assert_called_once()
        self.assertEqual(bridge.end(), {"ended": True}, "ending twice is harmless")
        # A process id the game reported is stopped only while it is still this session's game.
        for command, expect in (("some-other-program --game-dir /elsewhere", "not this session's game"), (None, "already gone")):
            other = PreviewBridge(CTL, GAME, self.folder / "preview")
            other.start(self.hmod, approved=True)
            with self.subTest(command=command), mock.patch.dict(os.environ, {"FAKE_CTL_MODE": "quit-hangs"}), \
                    mock.patch("os.kill") as kill, mock.patch.object(PreviewBridge, "command_line", return_value=command):
                self.assertIn(expect, other.end()["how"])
                kill.assert_not_called()

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


class AdversarialGameTests(unittest.TestCase):
    """PB-001: a game (or a stand-in) that lies, answers ambiguously or half-answers never yields game-load."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.hmod = ruby_package(self.folder)

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, mode="", items=("ruby_demo:ruby",)):
        bridge = PreviewBridge(CTL, GAME, self.folder / "preview", sleep=lambda _s: None)
        with mock.patch.dict(os.environ, {"FAKE_CTL_MODE": mode}):
            bridge.start(self.hmod, approved=True)
            try:
                content = bridge.verify_items(list(items) if items is not None else None)
            finally:
                bridge.end()
        return content, bridge.evidence(screenshot=None, state=None, content=content)

    def test_lying_or_ambiguous_games_never_reach_game_load(self):
        cases = {
            "give-lies": "NOT_IN_INVENTORY",          # {"ok": true} and nothing in the inventory
            "substring": "NOT_IN_INVENTORY",          # the id only appears inside another stack's components
            "prefix": "NOT_IN_INVENTORY",             # ruby_demo:ruby_block is not ruby_demo:ruby
            "two": "WRONG_QUANTITY",                  # one asked, two arrived
            "malformed": "MALFORMED_INVENTORY",       # 8 hotbar slots
            "duplicate-slot": "MALFORMED_INVENTORY",  # two stacks claim slot 0
            "counts-mismatch": "AMBIGUOUS_INVENTORY", # counts disagree with the slots
            "list-reply": "MALFORMED_REPLY",          # not an object at all
        }
        for mode, reason in cases.items():
            with self.subTest(mode):
                content, evidence = self.session(mode)
                self.assertFalse(content["all_found"])
                self.assertEqual(content["checks"][0]["reason"], reason)
                self.assertEqual(evidence["level"], "launched")

    def test_a_game_that_accepts_any_id_confirms_nothing(self):
        content, evidence = self.session("accept-anything")
        self.assertTrue(content["checks"][0]["confirmed"], "the item itself did arrive")
        self.assertFalse(content["control"]["refused"])
        self.assertFalse(content["all_found"], "but a game that accepts unknown ids proves nothing about the package")
        self.assertEqual(evidence["level"], "launched")

    def test_only_items_the_package_defines_can_confirm_it(self):
        # Vanilla items exist in every game: confirming one would say nothing about the mod.
        content, evidence = self.session("", items=("minecraft:diamond", "ruby_demo:not_in_the_package"))
        self.assertEqual([c["reason"] for c in content["checks"]], ["NOT_IN_PACKAGE", "NOT_IN_PACKAGE"])
        self.assertEqual(evidence["level"], "launched")
        self.assertEqual(package_items(self.hmod), ("ruby_demo", {"ruby_demo:ruby", "ruby_demo:ruby_block"}))
        content, evidence = self.session("", items=None)
        self.assertEqual(content["checked"], ["ruby_demo:ruby", "ruby_demo:ruby_block"], "by default: every package item")
        self.assertEqual(evidence["level"], "game-load")

    def test_a_late_inventory_update_is_waited_for(self):
        content, evidence = self.session("late")
        self.assertTrue(content["all_found"])
        self.assertEqual(evidence["level"], "game-load")

    def test_a_package_changed_during_the_session_downgrades_the_evidence(self):
        bridge = PreviewBridge(CTL, GAME, self.folder / "preview", sleep=lambda _s: None)
        bridge.start(self.hmod, approved=True)
        content = bridge.verify_items()
        bridge.end()
        self.hmod.write_bytes(self.hmod.read_bytes() + b"tampered")
        evidence = bridge.evidence(screenshot=None, state=None, content=content)
        self.assertEqual(evidence["level"], "launched")
        self.assertTrue(any("package changed" in note for note in evidence["notes"]))

    def test_evidence_is_bound_and_a_tampered_record_no_longer_matches_its_digest(self):
        import hashlib
        content, evidence = self.session("")
        recompute = lambda e: hashlib.sha256(json.dumps({k: e[k] for k in ("binding", "level", "content")},
                                                        sort_keys=True).encode("utf-8")).hexdigest()
        self.assertEqual(recompute(evidence), evidence["digest"])
        evidence["binding"]["package_sha256"] = "0" * 64
        self.assertNotEqual(recompute(evidence), evidence["digest"])

    def test_inventory_replies_are_checked_against_the_upstream_schema(self):
        empty = lambda n: {"slot": n, "item": None}
        good = {"hotbar": [empty(n) for n in range(9)], "main": [empty(n) for n in range(9, 36)],
                "armor": [empty(n) for n in range(500, 504)], "offhand": empty(504), "carried": None, "counts": {}}
        self.assertEqual(parse_inventory(good)["counts"], {})
        stacked = json.loads(json.dumps(good))
        stacked["main"][0] = {"slot": 9, "item": "ruby_demo:ruby", "count": 3}
        stacked["carried"] = {"item": "ruby_demo:ruby", "count": 1}
        stacked["counts"] = {"ruby_demo:ruby": 4}
        self.assertEqual(parse_inventory(stacked)["counts"], {"ruby_demo:ruby": 4})
        broken = {
            "a bool slot": ("hotbar", 1, {"slot": True, "item": None}),
            "an id without a namespace": ("hotbar", 0, {"slot": 0, "item": "ruby", "count": 1}),
            "a zero count": ("hotbar", 0, {"slot": 0, "item": "ruby_demo:ruby", "count": 0}),
            "a text count": ("hotbar", 0, {"slot": 0, "item": "ruby_demo:ruby", "count": "1"}),
            "a slot out of place": ("main", 0, {"slot": 8, "item": None}),
        }
        for why, (group, index, entry) in broken.items():
            with self.subTest(why):
                bad = json.loads(json.dumps(good))
                bad[group][index] = entry
                with self.assertRaises(BridgeError) as refused:
                    parse_inventory(bad)
                self.assertEqual(refused.exception.code, "MALFORMED_INVENTORY")
        for missing in ("hotbar", "main", "armor", "offhand", "counts"):
            with self.subTest(missing=missing), self.assertRaises(BridgeError):
                parse_inventory({k: v for k, v in good.items() if k != missing})

    def test_version_replies_that_are_not_a_launch_api_are_refused(self):
        import subprocess
        # A blank reply is " ", not "": on Windows an empty environment value removes the variable.
        for raw in ("[]", "not json", " ", '"0.1.0"', '{"launch_api": "0.1.0", "options": "all"}'):
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {"FAKE_LAUNCH_REPLY": raw}):
                with self.assertRaises(BridgeError) as refused:
                    PreviewBridge(CTL, GAME, self.folder / "preview").check_version()
                self.assertIn(refused.exception.code, ("VERSION_UNKNOWN", "VERSION_UNSUPPORTED"))

        def hangs(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], 60)

        with self.assertRaises(BridgeError) as late:
            PreviewBridge(CTL, GAME, self.folder / "preview", run=hangs).check_version()
        self.assertEqual(late.exception.code, "VERSION_UNKNOWN")

    def test_one_session_at_a_time_and_failed_screenshots_leave_no_file(self):
        bridge = PreviewBridge(CTL, GAME, self.folder / "preview")
        session = bridge.start(self.hmod, approved=True)
        with self.assertRaises(BridgeError) as busy:
            bridge.start(self.hmod, approved=True)
        self.assertEqual(busy.exception.code, "SESSION_ACTIVE")
        with mock.patch.dict(os.environ, {"FAKE_CTL_MODE": "no-png"}), self.assertRaises(BridgeError):
            bridge.screenshot(self.folder / "copy.png")
        self.assertEqual(list((Path(session["folder"]) / "screenshots").iterdir()), [], "no partial file is kept")
        self.assertFalse((self.folder / "copy.png").exists())
        bridge.end()
        with self.assertRaises(BridgeError) as ended:
            bridge.verify_items()
        self.assertEqual(ended.exception.code, "NO_SESSION")


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


if __name__ == "__main__":
    unittest.main()
