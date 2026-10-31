"""HS-020: one transaction model for people and AI, proven end to end on a real workspace folder.

The numbered tests are the acceptance list of HS-020 (docs/architecture/TRANSACTIONS.md)."""
import copy
import hashlib
import http.client
import json
import random
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from security.request_policy import session_token
from studio import Handler, ThreadingHTTPServer, hmod_zip
from studio_core import vfx
from studio_core.ai_tools import revision
from studio_core.migrate import from_editor_state, to_editor_state, to_generator_request, upgrade
from studio_core.project_schema import dumps
from studio_core.transactions import (ALL_EDITS, MAX_ENTRIES, PROPOSAL_TTL, ProjectService, TransactionError,
                                      describe, diff_documents)
from studio_core.ai_tools import Session
from studio_core.workspace import WorkspaceStore

OFFICIAL_RUBY = "ee3e1c878ea41fbf710f749896bfdb92b23b18e21e67b016b57b95b96a8797e2"
PLUGIN_UID = "33333333-3333-4333-8333-333333333333"
VFX_UID = "11111111-1111-4111-8111-111111111111"


def ruby():
    return upgrade(json.loads((ROOT / "examples" / "ruby_demo.hstudio.json").read_text(encoding="utf-8")))


def rich():
    """Ruby demo plus everything a transaction must carry untouched: an effect, a plugin's object
    (unknown kind, an extra field, a value that looks like an AI asset reference), extensions, an
    unknown document field, an unknown project field and an engine target."""
    state = to_editor_state(ruby())
    state["effects"] = [{"id": "impact_spark", "uid": VFX_UID, **vfx.impact_spark()}]
    state["target"] = {"engine": "horizon", "revision": "3c1d4b398b1d3f5c2e6c3e0f7f1a6a1d2a9b8c7d"}
    state["carry"]["preserved_objects"] = [{"uid": PLUGIN_UID, "kind": "acme.widget", "id": "w1",
                                             "props": {"opaque": {"asset": "item:ruby"}, "n": [1, 2.5]},
                                             "meta": {"owner": "acme"}}]
    state["carry"]["extensions"] = {"acme.plugin": {"keep": [1, {"deep": True}]}}
    state["carry"]["document_extra"] = {"acme_note": "keep me"}
    state["carry"]["project_extra"] = {"acme_flag": True}
    return from_editor_state(state)


def edit(doc, change):
    state = to_editor_state(doc)
    change(state)
    return from_editor_state(state)


def find(doc, kind, object_id):
    return next(o for o in doc["objects"] if o["kind"] == kind and o["id"] == object_id)


def plugin_bytes(doc):
    return json.dumps([find(doc, "acme.widget", "w1"), find(doc, "vfx", "impact_spark"), doc["extensions"],
                       doc["acme_note"], doc["project"]["acme_flag"]], ensure_ascii=False)


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clock = Clock()
        self.service = ProjectService(WorkspaceStore(self.root), clock=self.clock)
        self.doc = rich()
        self.first = self.service.commit(self.doc, base_revision=None)

    def tearDown(self):
        self.tmp.cleanup()

    def disk(self, project_id="ruby_demo"):
        primary, _ = self.service.store.paths(project_id)
        return primary.read_bytes()

    def journal(self, project_id="ruby_demo"):
        return json.loads(self.service.journal_path(project_id).read_text(encoding="utf-8"))


class AcceptanceTests(Fixture):
    """The HS-020 list, in order, on one project."""

    def test_human_and_ai_edits_share_one_history_across_restart(self):
        # 1. A person edits the item.
        r0 = self.first["revision"]
        human = edit(self.doc, lambda s: s["items"][0].update(name="Polished Ruby"))
        one = self.service.commit(human, base_revision=r0, label="Rename ruby")
        r1 = one["revision"]
        self.assertEqual(one["entry"]["actor"], "editor")
        self.assertEqual(one["entry"]["changes"]["updated"][0]["fields"], ["name"])
        self.assertEqual(find(one["document"], "item", "ruby")["props"]["name"], "Polished Ruby")

        # 2. The AI proposes a change to the same item; nothing changes yet.
        proposal = self.service.propose("ruby_demo", {"intent": "update", "asset": "item:ruby",
                                                      "set": {"rarity": "epic", "name": "Star Ruby"}},
                                        base_revision=r1)
        self.assertTrue(proposal["simulated"], "the fixture provider is labelled as simulated")
        self.assertEqual(self.service.open("ruby_demo")["revision"], r1)
        self.assertEqual(revision(json.loads(self.disk())), r1)

        # 3. The person previews the diff: the item, each field, before and after.
        [change] = proposal["diff"]["assets"]
        self.assertEqual((change["change"], change["kind"], change["id"]), ("updated", "item", "ruby"))
        fields = {f["path"]: (f.get("before"), f.get("after")) for f in change["fields"]}
        self.assertEqual(fields, {"name": ("Polished Ruby", "Star Ruby"), "rarity": ("rare", "epic")})
        self.assertEqual(proposal["base_revision"], r1)

        # 4. The person commits the proposal.
        two = self.service.commit_proposal("ruby_demo", proposal["id"], expected_revision=r1)
        r2 = two["revision"]
        self.assertEqual((two["entry"]["actor"], two["history"]["undo"][0]["approved_by"]), ("ai:fixture", "editor"))
        self.assertEqual([e["label"] for e in two["history"]["undo"]], ["AI: change item ruby", "Rename ruby"])

        # 5. Undo restores the previous state (the person's edit) exactly.
        back = self.service.undo("ruby_demo", expected_revision=r2)
        self.assertEqual(back["revision"], r1)
        self.assertEqual(dumps(back["document"]), dumps(one["document"]))
        self.assertEqual(back["step"]["actor"], "ai:fixture")

        # 6. Redo reapplies it.
        again = self.service.redo("ruby_demo", expected_revision=r1)
        self.assertEqual(again["revision"], r2)
        self.assertEqual(dumps(again["document"]), dumps(two["document"]))

        # 7. Autosave preserved it: the workspace on disk is the committed document.
        self.assertEqual(self.disk(), dumps(two["document"]).encode("utf-8"))

        # 8. A restart (a new core over the same folder) restores the document and the history.
        restarted = ProjectService(WorkspaceStore(self.root), clock=self.clock)
        opened = restarted.open("ruby_demo")
        self.assertEqual((opened["revision"], opened["history_note"]), (r2, None))
        self.assertEqual([e["label"] for e in opened["history"]["undo"]], ["AI: change item ruby", "Rename ruby"])
        self.assertEqual(restarted.undo("ruby_demo", expected_revision=r2)["revision"], r1)
        self.assertEqual(restarted.undo("ruby_demo", expected_revision=r1)["revision"], r0)
        self.assertEqual(self.disk(), dumps(self.doc).encode("utf-8"))
        self.assertEqual([e["label"] for e in restarted.open("ruby_demo")["history"]["redo"]],
                         ["Rename ruby", "AI: change item ruby"])

        # 12. Effects and plugin data came through every step byte for byte.
        for state in (one, two, back, again, opened):
            self.assertEqual(plugin_bytes(state["document"]), plugin_bytes(self.doc))

    def test_9_a_stale_proposal_is_rejected_and_audited(self):
        r0 = self.first["revision"]
        proposal = self.service.propose("ruby_demo", {"intent": "update", "asset": "item:ruby", "set": {"rarity": "epic"}},
                                        base_revision=r0)
        moved = self.service.commit(edit(self.doc, lambda s: s["items"][0].update(name="Moved on")), base_revision=r0)
        with self.assertRaises(TransactionError) as stale:
            self.service.commit_proposal("ruby_demo", proposal["id"], expected_revision=moved["revision"])
        self.assertEqual((stale.exception.code, stale.exception.status), ("STALE_PROPOSAL", 409))
        self.assertEqual(self.disk(), dumps(moved["document"]).encode("utf-8"))
        with self.assertRaises(TransactionError) as gone:  # a stale proposal is dropped, not kept for later
            self.service.commit_proposal("ruby_demo", proposal["id"], expected_revision=moved["revision"])
        self.assertEqual(gone.exception.code, "UNKNOWN_PROPOSAL")
        self.assertIn("stale_proposal", [a["action"] for a in self.service.audit("ruby_demo")])

    def test_rejecting_and_expiring_proposals_change_nothing(self):
        r0 = self.first["revision"]
        ask = lambda: self.service.propose("ruby_demo", {"intent": "material_set", "material": "topaz"}, base_revision=r0)
        rejected = ask()
        self.assertEqual(self.service.reject("ruby_demo", rejected["id"])["revision"], r0)
        with self.assertRaises(TransactionError):
            self.service.commit_proposal("ruby_demo", rejected["id"], expected_revision=r0)
        expired = ask()
        self.clock.now += PROPOSAL_TTL + 1
        with self.assertRaises(TransactionError) as late:
            self.service.commit_proposal("ruby_demo", expired["id"], expected_revision=r0)
        self.assertEqual(late.exception.code, "UNKNOWN_PROPOSAL")
        self.assertEqual(self.disk(), dumps(self.doc).encode("utf-8"))
        actions = [a["action"] for a in self.service.audit("ruby_demo")]
        self.assertEqual(actions.count("proposed"), 2)
        self.assertIn("rejected", actions)

    def test_10_a_second_tab_cannot_silently_overwrite(self):
        r0 = self.first["revision"]
        tab_a = edit(self.doc, lambda s: s["blocks"][0].update(hardness=9))
        tab_b = edit(self.doc, lambda s: s["blocks"][0].update(hardness=1))
        won = self.service.commit(tab_a, base_revision=r0)
        for attempt in (lambda: self.service.commit(tab_b, base_revision=r0),
                        lambda: self.service.undo("ruby_demo", expected_revision=r0),
                        lambda: self.service.propose("ruby_demo", {"intent": "material_set", "material": "x"},
                                                     base_revision=r0),
                        lambda: self.service.commit(tab_b, base_revision=None)):
            with self.assertRaises(TransactionError) as conflict:
                attempt()
            self.assertEqual((conflict.exception.code, conflict.exception.status), ("REVISION_CONFLICT", 409))
            self.assertEqual(self.disk(), dumps(won["document"]).encode("utf-8"))
        self.assertEqual(conflict.exception.details["revision"], won["revision"], "the 409 names the revision to reload")
        # Keeping tab B's version is an explicit commit on the current revision, and it can be undone.
        kept = self.service.commit(tab_b, base_revision=won["revision"], label="Keep this tab's version")
        self.assertEqual(self.service.undo("ruby_demo", expected_revision=kept["revision"])["revision"], won["revision"])

    def test_11_a_failed_multi_operation_transaction_changes_nothing(self):
        r0 = self.first["revision"]
        before_disk, before_journal = self.disk(), self.service.journal_path("ruby_demo").read_bytes()

        class Broken:
            name = "broken"

            def propose(self, request, context):
                return [{"tool": "create_asset", "kind": "item", "id": "half", "props": {"name": "Half"}},
                        {"tool": "update_asset", "asset": "item:ruby", "set": {"name": "Changed"}},
                        {"tool": "update_asset", "asset": "item:does_not_exist", "set": {"name": "x"}}]

        class Invalid(Broken):
            name = "invalid"

            def propose(self, request, context):  # a buildable project is required: a recipe with no result is not
                return [{"tool": "create_asset", "kind": "recipe", "id": "nothing", "props": {
                    "type": "shaped", "result": None, "count": 1, "grid": [None] * 9}}]

        self.service.providers.update(broken=Broken, invalid=Invalid)
        for provider, code in (("broken", "UNKNOWN_ASSET"), ("invalid", "INVALID_RESULT")):
            with self.subTest(provider), self.assertRaises(TransactionError) as failed:
                self.service.propose("ruby_demo", {}, provider=provider, base_revision=r0)
            self.assertEqual(failed.exception.code, code)
        self.assertEqual(self.disk(), before_disk)
        self.assertEqual(self.service.open("ruby_demo")["history"], {"undo": [], "redo": []})
        self.assertEqual(self.service.proposals, {})
        journal = self.journal()
        self.assertEqual(json.loads(before_journal)["entries"], journal["entries"])
        self.assertEqual([a["action"] for a in journal["audit"]][-2:], ["proposal_refused", "proposal_refused"])

    def test_13_the_hmod_stays_consistent_with_the_committed_project(self):
        r0 = self.first["revision"]
        self.assertEqual(hashlib.sha256(hmod_zip(to_generator_request(self.doc))).hexdigest(), OFFICIAL_RUBY,
                         "effects and plugin data never change the package")
        proposal = self.service.propose("ruby_demo", {"intent": "material_set", "material": "topaz", "rarity": "rare"},
                                        base_revision=r0)
        made = self.service.commit_proposal("ruby_demo", proposal["id"], expected_revision=r0)
        # What the editor would export (its state through the generator) is what the core committed.
        exported = hmod_zip(to_generator_request(from_editor_state(to_editor_state(made["document"]))))
        self.assertEqual(exported, hmod_zip(to_generator_request(made["document"])))
        self.assertNotEqual(hashlib.sha256(exported).hexdigest(), OFFICIAL_RUBY)
        self.assertEqual(sorted(c["id"] for c in made["entry"]["changes"]["created"]),
                         ["topaz", "topaz_block", "topaz_block", "topaz_from_block"])
        undone = self.service.undo("ruby_demo", expected_revision=made["revision"])
        self.assertEqual(hashlib.sha256(hmod_zip(to_generator_request(undone["document"]))).hexdigest(), OFFICIAL_RUBY)
        redone = self.service.redo("ruby_demo", expected_revision=undone["revision"])
        self.assertEqual(hmod_zip(to_generator_request(redone["document"])), exported,
                         "redo replays the recorded result: the same uids, the same package")


class VfxTransactionTests(unittest.TestCase):
    """§8: an AI-created effect goes through the same executor and history as every edit."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.service = ProjectService(WorkspaceStore(self.root))
        self.doc = ruby()
        self.r0 = self.service.commit(self.doc, base_revision=None)["revision"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_vfx_asset_preview_accept_undo_redo_edit_reopen_and_render(self):
        proposal = self.service.propose("ruby_demo", {"intent": "impact_effect", "id": "hit", "name": "Hit", "seed": 7},
                                        base_revision=self.r0)
        self.assertEqual([op["tool"] for op in proposal["operations"]], ["create_vfx_asset"])
        [created] = proposal["diff"]["assets"]
        self.assertEqual((created["change"], created["kind"], created["id"]), ("created", "vfx", "hit"))
        self.assertIn("VFX_STUDIO_ONLY", [d["code"] for d in proposal["diagnostics"]], "the result says it is not exported")
        made = self.service.commit_proposal("ruby_demo", proposal["id"], expected_revision=self.r0)
        effect = find(made["document"], "vfx", "hit")
        self.assertEqual((effect["props"]["seed"], effect["props"]["name"]), (7, "Hit"))
        self.assertEqual(vfx.validate(effect["props"]), [])
        # Game export stays the package without the effect: the officially checked bytes.
        self.assertEqual(hashlib.sha256(hmod_zip(to_generator_request(made["document"]))).hexdigest(), OFFICIAL_RUBY)
        frames = [vfx.simulate(effect["props"], t) for t in (0.0, 0.1, 0.3)]
        back = self.service.undo("ruby_demo", expected_revision=made["revision"])
        self.assertNotIn("vfx", [o["kind"] for o in back["document"]["objects"]])
        again = self.service.redo("ruby_demo", expected_revision=back["revision"])
        self.assertEqual(find(again["document"], "vfx", "hit")["uid"], effect["uid"], "redo gives the same uid")
        # A person then edits the effect in the VFX Studio (an ordinary editor commit).
        def tune(state):
            state["effects"][0]["emitters"][0]["bursts"][0]["count"] = 40
        edited = self.service.commit(edit(again["document"], tune), base_revision=again["revision"])
        self.assertEqual(edited["entry"]["changes"]["updated"][0]["fields"], ["emitters"])
        # Saved and reopened by a new core: the same effect renders the same particles.
        reopened = ProjectService(WorkspaceStore(self.root)).open("ruby_demo")
        self.assertEqual(reopened["revision"], edited["revision"])
        props = find(reopened["document"], "vfx", "hit")["props"]
        self.assertEqual(props["emitters"][0]["bursts"][0]["count"], 40)
        undone = ProjectService(WorkspaceStore(self.root)).undo("ruby_demo", expected_revision=edited["revision"])
        self.assertEqual([vfx.simulate(find(undone["document"], "vfx", "hit")["props"], t) for t in (0.0, 0.1, 0.3)], frames,
                         "deterministic: the same seed and data give the same particles after every round trip")

    def test_invalid_effects_and_unknown_presets_are_refused_before_anything_changes(self):
        from studio_core.ai_tools import Session, ToolError
        session = Session(self.doc)
        for op, code in (({"tool": "create_vfx_asset", "id": "x", "preset": "dragon_breath"}, "BAD_REQUEST"),
                         ({"tool": "create_vfx_asset", "id": "x", "set": {"emitters": []}}, "BAD_REQUEST"),
                         ({"tool": "create_vfx_asset", "id": "x", "set": {"duration": 0}}, "INVALID_RESULT"),
                         ({"tool": "create_vfx_asset", "id": "Bad Id"}, "INVALID_RESULT")):
            with self.subTest(op=op), self.assertRaises(ToolError) as refused:
                session.propose([op], actor="ai:test", expected_revision=session.revision)
            self.assertEqual(refused.exception.code, code)
        self.assertEqual(self.service.open("ruby_demo")["revision"], self.r0)


class JournalTests(Fixture):
    def test_a_new_edit_drops_the_redo_steps_and_history_is_bounded(self):
        rev = self.first["revision"]
        a = self.service.commit(edit(self.doc, lambda s: s["blocks"][0].update(hardness=7)), base_revision=rev)
        back = self.service.undo("ruby_demo", expected_revision=a["revision"])
        b = self.service.commit(edit(self.doc, lambda s: s["blocks"][0].update(hardness=2)), base_revision=back["revision"])
        self.assertEqual(b["history"]["redo"], [])
        with self.assertRaises(TransactionError) as nothing:
            self.service.redo("ruby_demo", expected_revision=b["revision"])
        self.assertEqual(nothing.exception.code, "NOTHING_TO_REDO")
        rev, doc = b["revision"], b["document"]
        for n in range(MAX_ENTRIES + 5):
            doc = edit(doc, lambda s, n=n: s["blocks"][0].update(hardness=n % 50 + 1, light=n % 15))
            rev = self.service.commit(doc, base_revision=rev)["revision"]
        journal = self.journal()
        self.assertEqual((len(journal["entries"]), journal["cursor"]), (MAX_ENTRIES, MAX_ENTRIES))
        for _ in range(MAX_ENTRIES):
            rev = self.service.undo("ruby_demo", expected_revision=rev)["revision"]
        with self.assertRaises(TransactionError) as empty:
            self.service.undo("ruby_demo", expected_revision=rev)
        self.assertEqual(empty.exception.code, "NOTHING_TO_UNDO")

    def test_no_change_is_no_entry(self):
        same = self.service.commit(copy.deepcopy(self.doc), base_revision=self.first["revision"])
        self.assertIsNone(same["entry"])
        self.assertEqual(same["history"]["undo"], [])

    def test_a_crash_between_the_workspace_and_the_journal_keeps_the_document(self):
        r0 = self.first["revision"]
        a = self.service.commit(edit(self.doc, lambda s: s["blocks"][0].update(hardness=7)), base_revision=r0)
        with mock.patch.object(ProjectService, "_save_journal", side_effect=OSError("power cut")):
            with self.assertRaises(OSError):
                self.service.commit(edit(a["document"], lambda s: s["blocks"][0].update(hardness=8)),
                                    base_revision=a["revision"])
        reopened = ProjectService(WorkspaceStore(self.root), clock=self.clock).open("ruby_demo")
        self.assertEqual(find(reopened["document"], "block", "ruby_block")["props"]["hardness"], 8, "the edit is on disk")
        self.assertEqual(reopened["history_note"], "reset", "and the response says the history could not be kept")
        self.assertEqual(reopened["history"], {"undo": [], "redo": []})
        self.assertIn("history_reset", [a["action"] for a in self.journal()["audit"]])

    def test_a_recovery_from_the_backup_moves_the_cursor_instead_of_losing_history(self):
        r0 = self.first["revision"]
        a = self.service.commit(edit(self.doc, lambda s: s["blocks"][0].update(hardness=7)), base_revision=r0)
        b = self.service.commit(edit(a["document"], lambda s: s["blocks"][0].update(hardness=8)), base_revision=a["revision"])
        primary, _ = self.service.store.paths("ruby_demo")
        primary.write_bytes(b"{damaged")
        opened = ProjectService(WorkspaceStore(self.root), clock=self.clock).open("ruby_demo")
        self.assertTrue(opened["recovered_from_backup"])
        self.assertEqual((opened["revision"], opened["history_note"]), (a["revision"], "reconciled"))
        self.assertEqual(len(opened["history"]["undo"]), 1)
        self.assertEqual(len(opened["history"]["redo"]), 1, "the lost step can be redone")
        service = ProjectService(WorkspaceStore(self.root), clock=self.clock)
        self.assertEqual(service.redo("ruby_demo", expected_revision=a["revision"])["revision"], b["revision"])

    def test_an_unreadable_journal_is_reset_and_the_document_is_untouched(self):
        self.service.journal_path("ruby_demo").write_text('{"schema": "something else"}', encoding="utf-8")
        opened = self.service.open("ruby_demo")
        self.assertEqual((opened["history_note"], opened["revision"]), ("reset", self.first["revision"]))
        self.assertEqual(dumps(opened["document"]), dumps(self.doc))

    def test_a_tampered_journal_step_is_refused_not_replayed(self):
        r0 = self.first["revision"]
        a = self.service.commit(edit(self.doc, lambda s: s["blocks"][0].update(hardness=7)), base_revision=r0)
        journal = self.journal()
        journal["entries"][0]["inverse"] = [{"tool": "update_asset", "uid": journal["entries"][0]["inverse"][0]["uid"],
                                             "set": {"hardness": 99}}]
        self.service.journal_path("ruby_demo").write_text(json.dumps(journal), encoding="utf-8")
        with self.assertRaises(TransactionError) as diverged:
            self.service.undo("ruby_demo", expected_revision=a["revision"])
        self.assertEqual(diverged.exception.code, "HISTORY_DIVERGED")
        self.assertEqual(self.disk(), dumps(a["document"]).encode("utf-8"))


class DiffTests(unittest.TestCase):
    def check(self, before, after):
        ops = diff_documents(before, after)
        if dumps(before) == dumps(after):
            self.assertEqual(ops, [])
            return
        result, _ = Session(before).plan(ops, allowed=ALL_EDITS, literal=True)
        self.assertEqual(dumps(result), dumps(after))

    def test_diffs_are_exact_for_random_edits_including_key_order_and_plugin_objects(self):
        rng = random.Random(20261031)
        base = rich()
        for trial in range(300):
            before, after = copy.deepcopy(base), copy.deepcopy(base)
            for _ in range(rng.randint(1, 6)):
                target = rng.choice([before, after])
                choice = rng.randrange(10)
                objects = target["objects"]
                free = [o for o in objects if o["kind"] not in ("recipe", "vfx")]  # schema-checked props stay valid
                if choice == 0 and free:
                    obj = rng.choice(free)
                    obj["props"][f"k{rng.randrange(5)}"] = rng.choice([1, "x", None, [1, {"asset": "item:ruby"}]])
                elif choice == 1 and free:
                    obj = rng.choice(free)
                    if obj["props"]:
                        obj["props"].pop(rng.choice(list(obj["props"])))
                elif choice == 2 and objects:
                    rng.shuffle(objects)
                elif choice == 3 and objects:
                    obj = rng.choice(objects)
                    obj["props"] = dict(reversed(list(obj["props"].items())))
                elif choice == 4:
                    uid = f"{rng.randrange(16**8):08x}-0000-4000-8000-{rng.randrange(16**12):012x}"
                    extra = {"meta": 1} if rng.random() < 0.3 else {}
                    objects.append({"uid": uid, "kind": rng.choice(["item", "acme.thing"]), "id": f"n{trial}_{uid[:4]}",
                                    "props": {"name": "N"}, **extra})
                elif choice == 5 and len(objects) > 1:
                    objects.remove(rng.choice([o for o in objects if o["kind"] != "recipe"] or objects))
                elif choice == 6:
                    target["extensions"][f"x{rng.randrange(3)}"] = rng.randrange(9)
                elif choice == 7:
                    target.pop(rng.choice(["target", "acme_note", "source_overrides", "provenance"]), None)
                elif choice == 8:
                    target["project"]["name"] = rng.choice(["A", "B"])
                    target["project"] = dict(reversed(list(target["project"].items())))
                else:
                    items = list(target.items())
                    rng.shuffle(items)
                    target.clear()
                    target.update(items)
            with self.subTest(trial=trial):
                self.check(before, after)
                self.check(after, before)

    def test_the_review_diff_names_assets_and_document_fields(self):
        before = rich()
        after = edit(before, lambda s: (s["items"][0].update(name="New"), s.pop("target")))
        view = describe(before, after)
        self.assertEqual([(a["change"], a["id"]) for a in view["assets"]], [("updated", "ruby")])
        self.assertEqual(view["document"], ["target"])
        self.assertEqual(view["labels"][PLUGIN_UID], "acme.widget:w1")


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.studio_workspaces = WorkspaceStore(Path(self.tmp.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def post(self, path, body, token=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Studio-Token"] = session_token(self.server)
        connection.request("POST", path, json.dumps(body), headers)
        response = connection.getresponse()
        status, data = response.status, json.loads(response.read())
        connection.close()
        return status, data

    def test_the_command_protocol_end_to_end(self):
        state = to_editor_state(rich())
        for path in ("/api/tx/open", "/api/tx/commit", "/api/tx/undo", "/api/ai/propose", "/api/ai/commit", "/api/ai/reject"):
            self.assertEqual(self.post(path, {"project_id": "ruby_demo"}, token=False)[0], 403, path)
        self.assertEqual(self.post("/api/tx/open", {"project_id": "ruby_demo"})[0], 404)
        status, first = self.post("/api/tx/commit", {"state": state, "base_revision": None})
        self.assertEqual(status, 200)
        self.assertEqual(first["state"], state, "the editor's state comes back unchanged")
        changed = copy.deepcopy(state)
        changed["items"][0]["name"] = "Polished"
        status, one = self.post("/api/tx/commit", {"state": changed, "base_revision": first["revision"], "label": "Rename"})
        self.assertEqual((status, one["history"]["undo"][0]["label"]), (200, "Rename"))
        status, stale = self.post("/api/tx/commit", {"state": state, "base_revision": first["revision"]})
        self.assertEqual((status, stale["code"], stale["revision"]), (409, "REVISION_CONFLICT", one["revision"]))
        status, proposal = self.post("/api/ai/propose", {"project_id": "ruby_demo", "base_revision": one["revision"],
                                                         "request": {"intent": "material_set", "material": "topaz"}})
        self.assertEqual((status, proposal["simulated"], proposal["provider"]), (200, True, "fixture"))
        status, made = self.post("/api/ai/commit", {"project_id": "ruby_demo", "proposal_id": proposal["id"],
                                                    "expected_revision": one["revision"]})
        self.assertEqual(status, 200)
        self.assertIn("topaz", [i["id"] for i in made["state"]["items"]])
        status, undone = self.post("/api/tx/undo", {"project_id": "ruby_demo", "expected_revision": made["revision"]})
        self.assertEqual((status, undone["state"]), (200, changed))
        status, redone = self.post("/api/tx/redo", {"project_id": "ruby_demo", "expected_revision": undone["revision"]})
        self.assertEqual((status, redone["revision"]), (200, made["revision"]))
        status, opened = self.post("/api/tx/open", {"project_id": "ruby_demo"})
        self.assertEqual((status, opened["state"], opened["revision"]), (200, made["state"], made["revision"]))
        status, history = self.post("/api/tx/history", {"project_id": "ruby_demo"})
        self.assertEqual(status, 200)
        self.assertEqual([a["action"] for a in history["audit"]],
                         ["created", "commit", "conflict", "proposed", "commit", "undo", "redo"])
        # The older whole-state write goes into the same journal.
        legacy = copy.deepcopy(made["state"])
        legacy["metadata"]["name"] = "Written the old way"
        status, wrote = self.post("/api/workspace/write", {"state": legacy, "expected_revision": made["revision"]})
        self.assertEqual(status, 200)
        status, opened = self.post("/api/tx/open", {"project_id": "ruby_demo"})
        self.assertEqual((opened["revision"], opened["history"]["undo"][0]["label"]), (wrote["revision"], "Workspace write"))
        for body, code in (({"project_id": "../evil"}, 400), ({"project_id": "ruby_demo", "proposal_id": "nope"}, 404)):
            self.assertEqual(self.post("/api/ai/reject", body)[0], code)
        status, refused = self.post("/api/ai/propose", {"project_id": "ruby_demo", "base_revision": wrote["revision"],
                                                        "provider": "claude", "request": {}})
        self.assertEqual((status, refused["code"]), (400, "UNKNOWN_PROVIDER"), "no live provider is wired in yet")


if __name__ == "__main__":
    unittest.main()
