"""Test the standalone Windows entrypoint without a visible desktop."""
import unittest
from launcher import app_version, smoke_test, start_server


class LauncherTests(unittest.TestCase):
    def test_version(self):
        self.assertRegex(app_version(), r'^\d+\.\d+\.\d+$')

    def test_server_uses_ephemeral_port_for_smoke(self):
        server = start_server(smoke_test=True)
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
            self.assertGreater(server.server_port, 0)
        finally:
            server.server_close()

    def test_bundled_application_smoke(self):
        self.assertEqual(smoke_test(), 0)

    def test_smoke_report_and_relaunch_recovers_the_workspace(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            report, workspace = Path(folder) / "report.json", Path(folder) / "workspace"
            self.assertEqual(smoke_test(report, workspace), 0)
            first = json.loads(report.read_text())
            self.assertTrue(first["ok"])
            self.assertEqual(first["checks"]["workspace_before_launch"], "empty")
            self.assertEqual(first["checks"]["hmod_sha256"], "ee3e1c878ea41fbf710f749896bfdb92b23b18e21e67b016b57b95b96a8797e2")
            self.assertEqual(smoke_test(report, workspace), 0)
            self.assertEqual(json.loads(report.read_text())["checks"]["workspace_before_launch"], "recovered")

    def test_smoke_failure_is_reported_not_hidden(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "report.json"
            with patch("studio.WEB_SCRIPTS", {"missing.js": b"x"}):
                self.assertEqual(smoke_test(report), 1)
            result = json.loads(report.read_text())
            self.assertFalse(result["ok"])
            self.assertIn("missing.js", result["error"])


if __name__ == "__main__":
    unittest.main()
