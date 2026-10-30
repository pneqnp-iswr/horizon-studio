"""Version metadata must not regress between releases."""
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_release_metadata import check_release_metadata


class ReleaseMetadataTests(unittest.TestCase):
    def test_repository_version_strings_consistent(self):
        self.assertEqual(check_release_metadata(), [])

    def test_checker_rejects_stale_notes_and_bad_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "VERSION").write_text("0.6.0\n", encoding="utf-8")
            (root / "RELEASE_NOTES.md").write_text("# Horizon Studio 0.5.0\n", encoding="utf-8")
            (root / "CHANGELOG.md").write_text("## 0.6.0 \n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs/FEATURE_MATRIX.md").write_text("# Capability matrix — Horizon Studio 0.6\n", encoding="utf-8")
            (root / "README.md").write_text("badge/version-0.6.0-blue\nVersion **0.6 ", encoding="utf-8")
            (root / "README.ru.md").write_text("Версия **0.6 ", encoding="utf-8")
            self.assertTrue(any("RELEASE_NOTES.md" in error for error in check_release_metadata(root)))
            (root / "VERSION").write_text("invalid\n", encoding="utf-8")
            self.assertEqual(check_release_metadata(root), ["Invalid VERSION: 'invalid'"])


if __name__ == '__main__':
    unittest.main()
