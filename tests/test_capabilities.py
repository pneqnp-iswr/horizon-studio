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
        for expected in ("unsupported status", "needs an evidence document", "needs a note", "default must name"):
            self.assertIn(expected, problems)

    def test_cli_capabilities(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["capabilities", str(ROOT / "examples" / "workshop_showcase.hstudio.json"), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["profile"]["content_api"], "0.2")


if __name__ == "__main__":
    unittest.main()
