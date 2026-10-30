"""HS-008 engine capability registry."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from horizon_cli import main, read_document  # noqa: E402
from studio_core.capabilities import check, load_registry, requirements, validate_registry  # noqa: E402
from studio_core.project_schema import new_uid  # noqa: E402

REGISTRY = load_registry()


def example(name):
    return read_document(ROOT / "examples" / f"{name}.hstudio.json")


class CapabilityTests(unittest.TestCase):
    def test_examples_need_only_officially_checked_capabilities(self):
        for name in ("ruby_demo", "workshop_showcase", "voxel_showcase"):
            with self.subTest(name):
                self.assertEqual(check(example(name), REGISTRY)["diagnostics"], [])
        self.assertIn("content.block_tag", requirements(example("workshop_showcase")))
        self.assertNotIn("content.block_tag", requirements(example("ruby_demo")))

    def test_missing_capability_is_reported_not_built_silently(self):
        doc = example("ruby_demo")
        doc["objects"].append({"uid": new_uid(), "kind": "entity", "id": "fox", "props": {}})
        diagnostics = check(doc, REGISTRY)["diagnostics"]
        self.assertEqual([(d["code"], d["capability"]) for d in diagnostics],
                         [("ENGINE_CAPABILITY_MISSING", "kind.entity")])

    def test_engine_only_capability_explains_why(self):
        registry = copy.deepcopy(REGISTRY)
        registry["profiles"][0]["capabilities"]["content.recipe"] = {"status": "engine-only", "note": "test reason"}
        message = check(example("ruby_demo"), registry)["diagnostics"][0]["message"]
        self.assertIn("test reason", message)

    def test_unknown_engine_revision_promises_nothing(self):
        doc = example("ruby_demo")
        doc["target"] = {"engine": "horizon", "revision": "f" * 40}
        report = check(doc, REGISTRY)
        self.assertIsNone(report["profile"])
        self.assertEqual(report["diagnostics"][0]["code"], "ENGINE_PROFILE_UNKNOWN")

    def test_registry_validation(self):
        self.assertEqual(validate_registry(REGISTRY), [])
        broken = copy.deepcopy(REGISTRY)
        caps = broken["profiles"][0]["capabilities"]
        caps["content.item"] = {"status": "works-great"}
        caps["content.recipe"] = {"status": "official-static", "evidence": "docs/NOPE.md"}
        caps["shader.pack"] = {"status": "engine-only"}
        broken["default"] = "0" * 40
        problems = " | ".join(validate_registry(broken))
        for expected in ("unsupported status", "docs/NOPE.md does not exist", "needs a note", "default must name",
                         "content.item: missing api, stability, side, backend, permissions, contract, source"):
            self.assertIn(expected, problems)

    def test_registry_fields_follow_horizon_api_levels(self):
        broken = copy.deepcopy(REGISTRY)
        caps = broken["profiles"][0]["capabilities"]
        caps["content.block"]["stability"] = "beta"
        caps["content.item"]["side"] = "everywhere"
        caps["content.lang"]["backend"] = "jar"
        caps["content.recipe"]["permissions"] = "registries"
        caps["content.loot_table"]["backend"] = None
        problems = " | ".join(validate_registry(broken))
        for expected in ("content.block: stability must be one of", "content.item: side must be one of",
                         "content.lang: unknown backend 'jar'", "content.recipe: permissions must be a list",
                         "content.loot_table: official-static needs the backend"):
            self.assertIn(expected, problems)
        native = REGISTRY["profiles"][0]["capabilities"]["native.hook_mod"]
        self.assertEqual((native["backend"], native["stability"]), ("hnmod", "experimental"))
        self.assertIn("not sandboxed", native["permissions"][0])

    def test_frozen_app_loads_the_registry_without_its_evidence_docs(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(validate_registry(REGISTRY, None), [])
            self.assertTrue(validate_registry(REGISTRY, Path(empty)), "the repository check still needs the documents")

    def test_cli_capabilities(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["capabilities", str(ROOT / "examples" / "workshop_showcase.hstudio.json"), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["profile"]["content_api"], "0.2")


if __name__ == "__main__":
    unittest.main()
