"""Moving from the 0.7 EXE to the desktop build: real files written by v0.7.0.

`tests/fixtures/legacy_0_7/` was produced by running the v0.7.0 tag's own core (c816211) with an
isolated HOME:
- it opened two example projects;
- it edited each one;
- it autosaved a disk workspace, saved the project file, and built the package.

`record.json` keeps 0.7's revisions and package hashes. The current core must read every one of those
files, keep their bytes, build the same packages, and put them into the HS-020 history without losing
anything."""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio import hmod_zip
from studio_core.migrate import from_editor_state, to_editor_state, to_generator_request, upgrade
from studio_core.project_schema import dumps
from studio_core.transactions import ProjectService
from studio_core.workspace import WorkspaceStore

LEGACY = ROOT / "tests" / "fixtures" / "legacy_0_7"
RECORD = json.loads((LEGACY / "record.json").read_text(encoding="utf-8"))


class FilesFrom07Tests(unittest.TestCase):
    def test_the_fixtures_are_what_0_7_wrote(self):
        self.assertEqual(RECORD["version"], "0.7.0")
        self.assertEqual(sorted(RECORD["projects"]), ["ruby_demo", "workshop_showcase"])

    def test_project_files_saved_by_0_7_open_unchanged_and_build_the_same_package(self):
        for name, record in RECORD["projects"].items():
            with self.subTest(name):
                saved = (LEGACY / f"{name}.saved-by-0.7.hstudio.json").read_bytes()
                self.assertEqual(hashlib.sha256(saved).hexdigest(), record["saved_sha256"])
                doc = upgrade(json.loads(saved))
                self.assertEqual(dumps(doc).encode("utf-8"), saved, "the canonical bytes did not change")
                self.assertEqual(hashlib.sha256(hmod_zip(to_generator_request(doc))).hexdigest(), record["hmod_sha256"],
                                 "the same project builds the same .hmod as 0.7")
                # 0.7's editor state (what its browser tab kept) is the same project today.
                state = json.loads((LEGACY / f"{name}.editor-state-0.7.json").read_text(encoding="utf-8"))
                self.assertEqual(dumps(from_editor_state(state)), dumps(doc))
                self.assertEqual(from_editor_state(to_editor_state(doc)), doc)

    def test_0_7_disk_workspaces_join_the_transaction_history(self):
        with tempfile.TemporaryDirectory() as folder:
            workspaces = Path(folder) / ".horizon-studio" / "workspaces"
            shutil.copytree(LEGACY / "workspaces", workspaces)
            before = {p.name: p.read_bytes() for p in workspaces.iterdir()}
            service = ProjectService(WorkspaceStore(workspaces))
            for name, record in RECORD["projects"].items():
                with self.subTest(name):
                    opened = service.open(name)
                    self.assertEqual(opened["revision"], record["workspace_revision"], "found under the same revision")
                    self.assertFalse(opened["recovered_from_backup"])
                    self.assertEqual((opened["history"], opened["history_note"]), ({"undo": [], "redo": []}, None),
                                     "0.7 kept no history on disk; the new one starts empty, without a warning")
                    self.assertIn("(edited in 0.7)", opened["document"]["project"]["description"])
                    # The first edit in the desktop build is an ordinary, undoable step.
                    state = to_editor_state(opened["document"])
                    state["metadata"]["name"] = "Moved to the desktop build"
                    edited = service.commit(from_editor_state(state), base_revision=opened["revision"])
                    back = service.undo(name, expected_revision=edited["revision"])
                    self.assertEqual(back["revision"], record["workspace_revision"])
            after = {p.name: p.read_bytes() for p in workspaces.iterdir() if p.name in before}
            self.assertEqual(after, before, "after undo, 0.7's workspace files hold exactly their old bytes")
            self.assertTrue(any(p.name.endswith(".journal.json") for p in workspaces.iterdir()),
                            "the history lives in its own file next to them")


    def test_rolling_back_to_0_7_keeps_new_data_opaque_and_intact(self):
        # The real 0.7 core saved a current project (effect, engine target, plugin object, extensions,
        # unknown fields) after a full editor round trip; nothing it does not understand was lost.
        sent = (LEGACY / RECORD["rollback"]["input"]).read_bytes()
        returned = (LEGACY / RECORD["rollback"]["saved_by_0_7"]).read_bytes()
        self.assertEqual(returned, sent)
        doc = upgrade(json.loads(returned))
        self.assertEqual(dumps(doc).encode("utf-8"), returned)
        kinds = {o["kind"] for o in doc["objects"]}
        self.assertTrue({"vfx", "acme.widget"} <= kinds)
        self.assertIn("target", doc)


if __name__ == "__main__":
    unittest.main()
