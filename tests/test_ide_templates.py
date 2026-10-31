"""IDE-003 starter gallery: real built-in fixtures, no network or game claims."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from studio_core import ide_templates
from studio_core.migrate import from_editor_state
from studio_core.project_schema import validate_document


class StarterTemplateTests(unittest.TestCase):
    def test_registry_uses_three_real_bundled_project_files(self):
        data = ide_templates.list_templates()
        self.assertEqual(data["schema"], ide_templates.SCHEMA)
        self.assertEqual([t["id"] for t in data["templates"]], ["ruby", "voxel", "workshop"])
        self.assertEqual([t["category"] for t in data["templates"]], ["content", "world", "mixed"])
        for template in data["templates"]:
            with self.subTest(template=template["id"]):
                path = Path(ide_templates.ROOT) / "examples" / next(
                    spec["file"] for spec in ide_templates.TEMPLATES if spec["id"] == template["id"])
                self.assertEqual(template["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertFalse(template["in_game_verified"])
                self.assertEqual(template["verification"], "project-schema-only")
                self.assertGreater(sum(template["counts"].values()), 0)

    def test_every_template_opens_as_roundtrippable_editor_state(self):
        for info in ide_templates.list_templates()["templates"]:
            with self.subTest(template=info["id"]):
                data = ide_templates.load_template(info["id"])
                self.assertEqual(data["sha256"], info["sha256"])
                self.assertEqual(data["schema"], ide_templates.SCHEMA)
                self.assertEqual(data["state"]["metadata"]["id"], info["project_id"])
                self.assertFalse(data["in_game_verified"])
                canonical = validate_document(from_editor_state(data["state"]))
                counts = {}
                for obj in canonical["objects"]:
                    counts[obj["kind"]] = counts.get(obj["kind"], 0) + 1
                self.assertEqual(counts, info["counts"])

    def test_reading_a_template_does_not_edit_the_fixture(self):
        before = {entry["id"]: ide_templates.load_template(entry["id"])["sha256"]
                  for entry in ide_templates.TEMPLATES}
        snapshot = ide_templates.load_template("ruby")["state"]
        snapshot["metadata"]["id"] = "changed"
        snapshot["items"].clear()
        after = {entry["id"]: ide_templates.load_template(entry["id"])["sha256"]
                 for entry in ide_templates.TEMPLATES}
        self.assertEqual(before, after)
        self.assertEqual(ide_templates.load_template("ruby")["state"]["metadata"]["id"], "ruby_demo")

    def test_unknown_template_paths_are_never_resolved(self):
        for name in ("../secrets", "/etc/passwd", "", "RUBY", "ruby?../../"):
            with self.subTest(name=name), self.assertRaises(KeyError):
                ide_templates.load_template(name)

    def test_missing_fixture_fails_closed_not_silent_empty_template(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(ide_templates, "ROOT", Path(temp)):
                with self.assertRaises(ide_templates.TemplateError):
                    ide_templates.list_templates()
                with self.assertRaises(ide_templates.TemplateError):
                    ide_templates.load_template("ruby")

    def test_malformed_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "examples"
            folder.mkdir()
            (folder / "ruby_demo.hstudio.json").write_text('{"schema":', encoding="utf-8")
            with mock.patch.object(ide_templates, "ROOT", Path(temp)):
                with self.assertRaises(ide_templates.TemplateError):
                    ide_templates.load_template("ruby")


if __name__ == "__main__":
    unittest.main()
