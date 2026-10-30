"""HS-005: studio.project/1 document, legacy migration, asset graph and CLI."""
import contextlib
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from horizon_cli import load_project, main
from security.request_policy import session_token
from studio import Handler, ThreadingHTTPServer, hmod_zip
from studio_core.graph import AssetGraph
from studio_core.migrate import from_editor_state, to_editor_state, to_generator_request, upgrade
from studio_core.project_schema import SCHEMA, ProjectFormatError, dumps, legacy_uid, new_uid
from studio_core.storage import atomic_write_bytes

EXAMPLES = ("ruby_demo", "workshop_showcase", "voxel_showcase")
# Packages accepted by the real cargo-horizon-mod at Horizon d2186eb (docs/COMPATIBILITY_EVIDENCE.md).
OFFICIALLY_CHECKED = {
    "ruby_demo": "ee3e1c878ea41fbf710f749896bfdb92b23b18e21e67b016b57b95b96a8797e2",
    "workshop_showcase": "b5fc8c688000531b78cf47fee60d158ce046b90be415f2b6e47e7e8093488452",
    "voxel_showcase": "56e6945d1885e154bfef96e22cb6b770e880e5059df9240a87ebade8e82df6ce",
}


def example(name):
    return json.loads((ROOT / "examples" / f"{name}.hstudio.json").read_text(encoding="utf-8"))


def legacy_request(data):
    """The pre-HS-005 CLI loader, kept verbatim as the reference for byte identity."""
    mod_id = data["metadata"]["id"]
    result = {**data["metadata"]}
    for group in ("blocks", "items", "recipes", "structures"):
        result[group] = data.get(group, [])
    converted = []
    for recipe in result["recipes"]:
        def convert(ref):
            return f"{mod_id}:{ref[1:]}" if isinstance(ref, str) and ref.startswith("@") else ref
        converted.append({**recipe, "result": convert(recipe.get("result")),
                          "grid": [convert(cell) for cell in recipe["grid"]]})
    result["recipes"] = converted
    return result


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MigrationGoldenTests(unittest.TestCase):
    def test_golden_documents(self):
        for name in EXAMPLES:
            with self.subTest(name):
                golden = (ROOT / "tests" / "fixtures" / "migration" / f"{name}.studio.json").read_text(encoding="utf-8")
                self.assertEqual(dumps(upgrade(example(name))), golden)

    def test_migrated_examples_build_officially_checked_bytes(self):
        for name in EXAMPLES:
            with self.subTest(name):
                migrated = hmod_zip(to_generator_request(upgrade(example(name))))
                self.assertEqual(migrated, hmod_zip(legacy_request(example(name))))
                self.assertEqual(sha(migrated), OFFICIALLY_CHECKED[name])
                golden = json.loads((ROOT / "tests" / "fixtures" / "migration" / f"{name}.studio.json").read_text())
                self.assertEqual(sha(hmod_zip(to_generator_request(golden))), OFFICIALLY_CHECKED[name])

    def test_migration_is_idempotent_and_deterministic(self):
        for name in EXAMPLES:
            with self.subTest(name):
                once = upgrade(example(name))
                self.assertEqual(upgrade(once), once)
                self.assertEqual(upgrade(example(name)), once)
                self.assertEqual(once["provenance"]["migrations"][0]["to"], SCHEMA)

    def test_recipes_reference_objects_by_uid(self):
        doc = upgrade(example("ruby_demo"))
        ruby = next(o for o in doc["objects"] if o["id"] == "ruby")
        self.assertEqual(ruby["uid"], legacy_uid("ruby_demo", "item", "ruby"))
        recipe = next(o for o in doc["objects"] if o["kind"] == "recipe" and o["id"] == "ruby_block")
        self.assertEqual(recipe["props"]["grid"], [{"ref": ruby["uid"]}] * 9)
        unpack = next(o for o in doc["objects"] if o["id"] == "ruby_from_block")
        self.assertEqual(unpack["props"]["grid"][1:], [None] * 8)


class EditorRoundTripTests(unittest.TestCase):
    def rich_document(self):
        doc = upgrade(example("workshop_showcase"))
        doc["project"]["homepage"] = "https://example.invalid/mod"
        doc["objects"].append({"uid": new_uid(), "kind": "plugin.particle", "id": "sparkle",
                               "props": {"rate": 12}})
        doc["extensions"]["plugin.particle"] = {"version": 3}
        doc["future_field"] = {"kept": True}
        return doc

    def test_open_edit_save_loses_nothing(self):
        for doc in [upgrade(example(name)) for name in EXAMPLES] + [self.rich_document()]:
            with self.subTest(doc["project"]["id"]):
                state = json.loads(json.dumps(to_editor_state(doc)))
                restored = from_editor_state(state)
                if any(o["kind"] == "plugin.particle" for o in doc["objects"]):
                    # Unknown kinds travel in carry and come back after the known objects.
                    self.assertEqual(restored["objects"][-1]["kind"], "plugin.particle")
                self.assertEqual(sorted(restored["objects"], key=lambda o: o["uid"]),
                                 sorted(doc["objects"], key=lambda o: o["uid"]))
                for field in ("project", "extensions", "provenance", "source_overrides"):
                    self.assertEqual(restored[field], doc[field])
                self.assertEqual(restored.get("future_field"), doc.get("future_field"))

    def test_editor_rename_keeps_uid_and_references(self):
        doc = upgrade(example("ruby_demo"))
        state = to_editor_state(doc)
        ruby = state["items"][0]
        old_uid = ruby["uid"]
        ruby["id"] = "gem"
        for recipe in state["recipes"]:  # the UI rewrites @refs on rename
            recipe["grid"] = ["@gem" if cell == "@ruby" else cell for cell in recipe["grid"]]
            recipe["result"] = "@gem" if recipe["result"] == "@ruby" else recipe["result"]
        saved = from_editor_state(state)
        gem = next(o for o in saved["objects"] if o["id"] == "gem")
        self.assertEqual(gem["uid"], old_uid)
        graph = AssetGraph(saved)
        self.assertEqual(len(graph.dependents(old_uid)), 2)
        request = to_generator_request(saved)
        self.assertEqual(request["recipes"][0]["grid"][0], "ruby_demo:gem")

    def test_renaming_in_the_document_needs_no_reference_rewrites(self):
        doc = upgrade(example("ruby_demo"))
        next(o for o in doc["objects"] if o["id"] == "ruby")["id"] = "gem"
        request = to_generator_request(doc)
        self.assertEqual(request["recipes"][0]["grid"], ["ruby_demo:gem"] * 9)
        self.assertEqual(request["recipes"][1]["result"], "ruby_demo:gem")

    def test_editor_state_without_uids_gets_derived_ones(self):
        state = {"metadata": {"id": "fresh", "name": "Fresh", "author": "A"},
                 "items": [{"id": "gem", "name": "Gem"}], "blocks": [], "recipes": [], "structures": []}
        doc = from_editor_state(state)
        self.assertEqual(doc["objects"][0]["uid"], legacy_uid("fresh", "item", "gem"))
        self.assertEqual(doc["provenance"], {})


class SourceOverrideTests(unittest.TestCase):
    """Regression: the CLI used to drop source_overrides saved by the editor."""

    def test_cli_build_keeps_editor_source_overrides(self):
        override_path = "assets/ruby_demo/models/item/ruby.json"
        override = json.dumps({"parent": "minecraft:item/handheld", "textures": {"layer0": "minecraft:item/emerald"}})
        data = example("ruby_demo")
        data["schema"] = 3
        data["source_overrides"] = {override_path: override}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ruby.hstudio.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            built = hmod_zip(load_project(path))
        editor_payload = {**legacy_request(data), "source_overrides": data["source_overrides"]}
        self.assertEqual(built, hmod_zip(editor_payload))
        self.assertNotEqual(built, hmod_zip(legacy_request(data)))


class GraphDiagnosticsTests(unittest.TestCase):
    def test_unknown_local_reference_keeps_legacy_meaning(self):
        data = example("ruby_demo")
        data["recipes"][0]["grid"][0] = "@missing"
        doc = upgrade(data)
        recipe = next(o for o in doc["objects"] if o["kind"] == "recipe")
        self.assertEqual(recipe["props"]["grid"][0], "ruby_demo:missing")
        codes = [d["code"] for d in AssetGraph(doc).diagnostics()]
        self.assertEqual(codes, ["UNRESOLVED_LOCAL_NAME"])
        with self.assertRaisesRegex(ValueError, "unknown ingredient"):
            hmod_zip(to_generator_request(doc))

    def test_missing_uid_reference(self):
        doc = upgrade(example("ruby_demo"))
        recipe = next(o for o in doc["objects"] if o["kind"] == "recipe")
        recipe["props"]["result"] = {"ref": new_uid()}
        self.assertEqual([d["code"] for d in AssetGraph(doc).diagnostics()], ["MISSING_REFERENCE"])
        with self.assertRaisesRegex(ValueError, "missing object"):
            to_generator_request(doc)
        with self.assertRaises(ProjectFormatError):
            to_editor_state(doc)

    def test_reference_to_non_content_kind(self):
        doc = upgrade(example("workshop_showcase"))
        structure = next(o for o in doc["objects"] if o["kind"] == "structure")
        recipe = next(o for o in doc["objects"] if o["kind"] == "recipe")
        recipe["props"]["grid"][0] = {"ref": structure["uid"]}
        self.assertIn("INVALID_REFERENCE_KIND", [d["code"] for d in AssetGraph(doc).diagnostics()])
        with self.assertRaisesRegex(ValueError, "not a block or item"):
            to_generator_request(doc)

    def test_unknown_kind_is_kept_but_not_built(self):
        doc = upgrade(example("ruby_demo"))
        doc["objects"].append({"uid": new_uid(), "kind": "entity", "id": "fox", "props": {}})
        diagnostics = AssetGraph(doc).diagnostics()
        self.assertEqual([(d["level"], d["code"]) for d in diagnostics], [("warning", "UNSUPPORTED_OBJECT_KIND")])
        self.assertEqual(sha(hmod_zip(to_generator_request(doc))), OFFICIALLY_CHECKED["ruby_demo"])

    def test_dependencies_and_dependents(self):
        doc = upgrade(example("workshop_showcase"))
        graph = AssetGraph(doc)
        uid = {o["id"]: o["uid"] for o in doc["objects"]}
        self.assertEqual(graph.dependencies(uid["beacon_craft"]), sorted([uid["beacon_block"], uid["shard"]]))
        self.assertEqual(graph.dependents(uid["shard"]), sorted([uid["beacon_craft"], uid["shard_from_vanilla"]]))
        self.assertEqual(graph.dependents(uid["arena"]), [])


class DocumentValidationTests(unittest.TestCase):
    def broken(self, mutate):
        doc = upgrade(example("ruby_demo"))
        mutate(doc)
        return doc

    def test_rejects_structural_errors(self):
        cases = {
            "duplicate uid": lambda d: d["objects"][1].update(uid=d["objects"][0]["uid"]),
            "uppercase uid": lambda d: d["objects"][0].update(uid=d["objects"][0]["uid"].upper()),
            "block/item id clash": lambda d: d["objects"][1].update(id="ruby_block"),
            "bad kind": lambda d: d["objects"][0].update(kind="Block"),
            "props not object": lambda d: d["objects"][0].update(props=[]),
            "bad object id": lambda d: d["objects"][0].update(id="Ruby Block"),
            "grid too long": lambda d: d["objects"][2]["props"].update(grid=[None] * 10),
            "bad ref": lambda d: d["objects"][2]["props"].update(result={"ref": "nope"}),
            "overrides not text": lambda d: d.update(source_overrides={"a.json": {}}),
            "wrong schema": lambda d: d.update(schema="studio.project/2"),
        }
        for label, mutate in cases.items():
            with self.subTest(label), self.assertRaises(ProjectFormatError):
                upgrade(self.broken(mutate))

    def test_rejects_non_projects(self):
        for data in (None, [], {"format": "other"}, {"format": "horizon-studio", "schema": 1},
                     {"format": "horizon-studio", "schema": 3}):
            with self.subTest(data), self.assertRaises(ProjectFormatError):
                upgrade(data)

    def test_legacy_extra_fields_are_preserved(self):
        data = example("ruby_demo")
        data["ui_layout"] = {"panel": "left"}
        doc = upgrade(data)
        self.assertEqual(doc["extensions"]["horizon-studio.legacy-fields"], {"ui_layout": {"panel": "left"}})


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.legacy = self.root / "ruby.hstudio.json"
        self.legacy.write_text(json.dumps(example("ruby_demo")), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_migrate_to_stdout_and_file(self):
        code, out, _ = self.run_cli("migrate", self.legacy)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["schema"], SCHEMA)
        target = self.root / "v1.hstudio.json"
        self.assertEqual(self.run_cli("migrate", self.legacy, "-o", target)[0], 0)
        self.assertEqual(target.read_text(encoding="utf-8"), out)
        code, _, err = self.run_cli("migrate", self.legacy, "-o", target)
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        self.assertEqual(self.run_cli("migrate", self.legacy, "-o", target, "--force")[0], 0)

    def test_in_place_migration_keeps_a_backup(self):
        original = self.legacy.read_bytes()
        code, out, _ = self.run_cli("migrate", self.legacy, "-o", self.legacy)
        self.assertEqual(code, 0, out)
        backup = self.root / "ruby.hstudio.json.schema2.bak"
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(json.loads(self.legacy.read_text())["schema"], SCHEMA)
        code, out, _ = self.run_cli("migrate", self.legacy, "-o", self.legacy)
        self.assertEqual(code, 0)
        self.assertIn("already", out)
        self.legacy.write_bytes(original)
        code, _, err = self.run_cli("migrate", self.legacy, "-o", self.legacy)
        self.assertEqual(code, 1)
        self.assertIn("Backup", err)
        self.assertEqual(self.legacy.read_bytes(), original)

    def test_build_from_v1_matches_legacy(self):
        v1 = self.root / "v1.hstudio.json"
        self.run_cli("migrate", self.legacy, "-o", v1)
        outputs = []
        for source in (self.legacy, v1):
            target = self.root / f"{source.stem}.hmod"
            self.assertEqual(self.run_cli("build", source, "-o", target)[0], 0)
            outputs.append(target.read_bytes())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(sha(outputs[0]), OFFICIALLY_CHECKED["ruby_demo"])

    def test_graph_command(self):
        code, out, _ = self.run_cli("graph", self.legacy, "--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(len(report["nodes"]), 4)
        self.assertEqual(len(report["edges"]), 4)
        broken = example("ruby_demo")
        broken["recipes"][0]["result"] = "@nothing"
        self.legacy.write_text(json.dumps(broken), encoding="utf-8")
        code, out, _ = self.run_cli("graph", self.legacy)
        self.assertEqual(code, 1)
        self.assertIn("UNRESOLVED_LOCAL_NAME", out)


class ProjectHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, path, body, **headers):
        port = self.server.server_address[1]
        sent = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json",
                "X-Studio-Token": session_token(self.server)}
        sent.update(headers)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("POST", path, body=json.dumps(body).encode(), headers=sent)
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_open_legacy_then_save_canonical(self):
        status, raw = self.post("/api/project/open", example("ruby_demo"))
        self.assertEqual(status, 200)
        opened = json.loads(raw)
        self.assertEqual(opened["migrated_from"], 2)
        self.assertEqual(opened["diagnostics"], [])
        state = opened["state"]
        self.assertEqual(state["recipes"][0]["grid"], ["@ruby"] * 9)
        self.assertTrue(all(entry["uid"] for entry in state["blocks"] + state["items"] + state["recipes"]))
        status, raw = self.post("/api/project/save", state)
        self.assertEqual(status, 200)
        saved = json.loads(raw)
        self.assertEqual(saved, upgrade(example("ruby_demo")))
        status, raw = self.post("/api/project/open", saved)
        self.assertIsNone(json.loads(raw)["migrated_from"])

    def test_project_routes_keep_the_api_security_policy(self):
        self.assertEqual(self.post("/api/project/save", {}, **{"X-Studio-Token": "wrong"})[0], 403)
        self.assertEqual(self.post("/api/project/open", {}, **{"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.post("/api/project/open", {}, Origin="http://evil.example")[0], 403)
        status, raw = self.post("/api/project/open", {"format": "horizon-studio", "schema": 99})
        self.assertEqual(status, 400)
        self.assertIn("Expected a Horizon Studio project", json.loads(raw)["error"])


class AtomicWriteTests(unittest.TestCase):
    def test_replaces_and_leaves_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "p.json"
            target.write_bytes(b"old")
            atomic_write_bytes(target, b"new")
            self.assertEqual(target.read_bytes(), b"new")
            self.assertEqual(os.listdir(folder), ["p.json"])

    def test_failed_replace_keeps_the_original(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "p.json"
            target.write_bytes(b"old")
            with patch("studio_core.storage.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    atomic_write_bytes(target, b"new")
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual(os.listdir(folder), ["p.json"])


if __name__ == "__main__":
    unittest.main()
