"""HS-020: the AI Creator tool contract and transactional executor, with deterministic fixtures."""
import base64
import copy
import hashlib
import itertools
import unittest
import uuid

from studio_core.ai_tools import FixtureProvider, Session, ToolError, revision, run_request
from studio_core.project_schema import validate_document

OFFICIAL_RUBY = "ee3e1c878ea41fbf710f749896bfdb92b23b18e21e67b016b57b95b96a8797e2"
EMPTY = {"format": "horizon-studio", "schema": "studio.project/1",
         "project": {"id": "ruby_demo", "name": "Ruby Demo", "version": "0.1.0", "author": "Creator",
                     "description": "Example with two recipes, a block and a gem"},
         "objects": [], "source_overrides": {}, "extensions": {}, "provenance": {}}
RUBY = {"intent": "material_set", "material": "ruby", "rarity": "rare", "hardness": 4, "light": 3}


def session(doc=EMPTY):
    counter = itertools.count(1)
    return Session(copy.deepcopy(doc), uid_factory=lambda: str(uuid.UUID(int=next(counter))), clock=lambda: 0.0)


class AiCreatorTests(unittest.TestCase):
    def test_a_structured_request_becomes_a_validated_transaction_with_officially_checked_bytes(self):
        s = session()
        proposal = run_request(s, FixtureProvider(), RUBY)
        self.assertEqual(s.revision, revision(EMPTY), "a proposal changes nothing")
        self.assertEqual([c["id"] for c in proposal.changes["created"]], ["ruby_block", "ruby", "ruby_block", "ruby_from_block"])
        self.assertFalse([d for d in proposal.diagnostics if d["level"] == "error"])
        transaction = s.commit(proposal.id, actor="human", expected_revision=revision(EMPTY))
        self.assertEqual(transaction.result_revision, s.revision)
        validate_document(s.doc)
        # References are by uid, never by name.
        recipe = next(o for o in s.doc["objects"] if o["id"] == "ruby_from_block")
        block = next(o for o in s.doc["objects"] if o["kind"] == "block")
        self.assertEqual(recipe["props"]["grid"][0], {"ref": block["uid"]})
        # Equivalent canonical projects build identical bytes: the ones the official checker accepted.
        built = s.call("build_project", actor="ai:fixture")
        self.assertEqual(built["hmod_sha256"], OFFICIAL_RUBY)

    def test_rollback_restores_the_exact_previous_document(self):
        s = session()
        base = s.revision
        t1 = s.apply(FixtureProvider().propose(RUBY, {}), actor="ai:fixture", expected_revision=base)
        after_create = s.revision
        ruby = next(o for o in s.doc["objects"] if o["id"] == "ruby")
        t2 = s.apply([{"tool": "update_asset", "uid": ruby["uid"], "set": {"rarity": "epic"}, "id": "gem"}],
                     actor="human", expected_revision=after_create)
        self.assertEqual(t2.changes["updated"][0]["fields"], ["id", "rarity"])
        with self.assertRaises(ToolError) as older:
            s.rollback(t1.id, actor="human", expected_revision=s.revision)
        self.assertEqual(older.exception.code, "NOT_LATEST")
        s.rollback(t2.id, actor="human", expected_revision=s.revision)
        self.assertEqual(s.revision, after_create)
        s.rollback(t1.id, actor="human", expected_revision=s.revision)
        self.assertEqual(s.revision, base)
        self.assertEqual(s.doc, EMPTY)

    def test_invalid_requests_change_nothing_and_are_audited(self):
        s = session()
        s.apply(FixtureProvider().propose(RUBY, {}), actor="ai:fixture", expected_revision=s.revision)
        good = copy.deepcopy(s.doc)
        ruby = next(o for o in s.doc["objects"] if o["id"] == "ruby")
        block = next(o for o in s.doc["objects"] if o["kind"] == "block")
        cases = {
            "UNKNOWN_TOOL": [{"tool": "run_shell", "command": "rm -rf /"}],
            "INVALID_RESULT": [{"tool": "create_asset", "kind": "block", "id": "Bad Id", "props": {"name": "x", "template": "minecraft:stone"}}],
            "GENERATOR": [{"tool": "update_asset", "uid": block["uid"], "set": {"hardness": 999}}],
            "DUPLICATE": [{"tool": "create_asset", "kind": "item", "id": "ruby", "props": {"name": "Again", "template": "minecraft:diamond"}}],
            "UNKNOWN_ASSET": [{"tool": "create_asset", "kind": "recipe", "id": "r", "props": {
                "type": "shapeless", "result": {"asset": "item:nope"}, "count": 1, "grid": [{"asset": "item:ruby"}] + [None] * 8}}],
            "IN_USE": [{"tool": "delete_asset", "uid": ruby["uid"]}],
            "SHADOW": [{"tool": "update_asset", "uid": ruby["uid"], "set": {"uid": "x"}}],
            "EMPTY": [],
        }
        for name, operations in cases.items():
            with self.subTest(name), self.assertRaises(ToolError) as refused:
                s.propose(operations, actor="ai:fixture", expected_revision=s.revision)
            self.assertTrue(refused.exception.code)
            self.assertEqual(s.doc, good, f"{name} must not change the project")
        rejected = [entry for entry in s.audit if entry["outcome"] == "rejected"]
        self.assertEqual(len(rejected), len(cases))
        self.assertTrue(all(len(entry["args_sha256"]) == 64 for entry in s.audit))
        # The session recovers: a valid edit still works after the rejections.
        s.apply([{"tool": "update_asset", "uid": ruby["uid"], "set": {"rarity": "uncommon"}}],
                actor="human", expected_revision=s.revision)
        self.assertEqual(next(o for o in s.doc["objects"] if o["id"] == "ruby")["props"]["rarity"], "uncommon")

    def test_revision_preconditions_and_cancellable_proposals(self):
        s = session()
        stale = s.revision
        proposal = run_request(s, FixtureProvider(), RUBY)
        other = s.propose([{"tool": "create_asset", "kind": "item", "id": "opal", "props": {
            "name": "Opal", "template": "minecraft:emerald"}}], actor="human", expected_revision=stale)
        s.commit(other.id, actor="human", expected_revision=stale)
        with self.assertRaises(ToolError) as conflict:
            s.commit(proposal.id, actor="human", expected_revision=stale)
        self.assertEqual(conflict.exception.code, "REVISION_CONFLICT")
        with self.assertRaises(ToolError) as old:
            s.commit(proposal.id, actor="human", expected_revision=s.revision)
        self.assertEqual(old.exception.code, "STALE_PROPOSAL")
        fresh = run_request(s, FixtureProvider(), RUBY)
        s.cancel(fresh.id, actor="human")
        with self.assertRaises(ToolError):
            s.commit(fresh.id, actor="human", expected_revision=s.revision)
        self.assertEqual([o["id"] for o in s.doc["objects"]], ["opal"])
        self.assertEqual([e["outcome"] for e in s.audit if e["tool"] == "cancel"], ["cancelled"])

    def test_privileged_export_needs_a_person_and_capability_gates_still_apply(self):
        s = session()
        s.apply(FixtureProvider().propose(RUBY, {}), actor="ai:fixture", expected_revision=s.revision)
        with self.assertRaises(ToolError) as needs:
            s.call("export_package", actor="ai:fixture")
        self.assertEqual(needs.exception.code, "APPROVAL_REQUIRED")
        exported = s.call("export_package", actor="human", approved=True)
        self.assertEqual(hashlib.sha256(base64.b64decode(exported["hmod_base64"])).hexdigest(), OFFICIAL_RUBY)
        # An unknown target keeps the project editable but refuses to build or export.
        target = copy.deepcopy(s.doc)
        target["target"] = {"engine": "horizon", "revision": "f" * 40}
        blocked = session(target)
        self.assertTrue(blocked.call("validate_project", actor="ai:fixture")["ok"])
        with self.assertRaises(ToolError) as engine:
            blocked.call("build_project", actor="ai:fixture")
        self.assertEqual(engine.exception.code, "ENGINE_CAPABILITY")

    def test_native_code_and_unknown_tools_are_not_part_of_the_contract(self):
        s = session()
        for tool in ("build_native", "run_rust", "create_asset", "rollback_transaction"):
            with self.subTest(tool), self.assertRaises(ToolError) as refused:
                s.call(tool, {}, actor="ai:fixture")
            self.assertEqual(refused.exception.code, "UNKNOWN_TOOL")
        info = s.call("inspect_project", actor="ai:fixture")
        self.assertNotIn("build_native", info["tools"])
        self.assertEqual(info["contract"], "horizon-studio.ai-tools/1")


class AiApplyCliTests(unittest.TestCase):
    def test_cli_applies_a_request_writes_the_project_and_the_audit(self):
        import contextlib
        import io
        import json
        import tempfile
        from pathlib import Path
        from horizon_cli import main
        from studio_core.project_schema import dumps
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            project, out, ops, audit = (folder / n for n in ("p.hstudio.json", "out.hstudio.json", "ops.json", "audit.jsonl"))
            project.write_text(dumps(EMPTY), encoding="utf-8")
            ops.write_text(json.dumps({"request": RUBY}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["ai-apply", str(project), "--operations", str(ops), "-o", str(out), "--audit", str(audit)]), 0)
            self.assertEqual(project.read_text(encoding="utf-8"), dumps(EMPTY), "the input project is never modified")
            built = io.StringIO()
            with contextlib.redirect_stdout(built):
                self.assertEqual(main(["build", str(out), "-o", str(folder / "ruby.hmod")]), 0)
            self.assertEqual(hashlib.sha256((folder / "ruby.hmod").read_bytes()).hexdigest(), OFFICIAL_RUBY)
            outcomes = [json.loads(line)["outcome"] for line in audit.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(outcomes, ["read", "proposed", "applied"])
            ops.write_text(json.dumps([{"tool": "delete_asset", "uid": "00000000-0000-0000-0000-000000000000"}]), encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(main(["ai-apply", str(out), "--operations", str(ops), "-o", str(folder / "x.json")]), 1)
            self.assertIn("UNKNOWN_ASSET", err.getvalue())
            self.assertFalse((folder / "x.json").exists())
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["ai-apply", str(out), "--operations", str(ops), "-o", str(out), "--force"]), 1)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["objects"][0]["id"], "ruby_block")


if __name__ == "__main__":
    unittest.main()
