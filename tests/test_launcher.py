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

    def test_core_serves_until_stdin_closes(self):
        """The desktop shell's contract: one JSON handshake line, a live server, stop on EOF."""
        import io
        import json
        import os
        import subprocess
        import sys
        import urllib.request
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        child = subprocess.Popen([sys.executable, str(root / "launcher.py"), "--serve"], cwd=root,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                 env={**os.environ, "PYTHONUNBUFFERED": "1"})
        try:
            ready = json.loads(child.stdout.readline())
            self.assertEqual((ready["protocol"], ready["event"]), ("horizon-studio.core/1", "ready"))
            self.assertRegex(ready["url"], r"^http://127\.0\.0\.1:\d+/$")
            self.assertEqual(ready["version"], app_version())
            with urllib.request.urlopen(ready["url"] + "api/session", timeout=10) as response:
                self.assertTrue(json.loads(response.read())["token"])
            with urllib.request.urlopen(ready["url"], timeout=10) as response:
                self.assertIn(b"Horizon Studio", response.read())
            child.stdin.close()  # what happens when the shell exits or crashes
            self.assertEqual(child.wait(timeout=15), 0)
            self.assertEqual(json.loads(child.stdout.readline())["event"], "stopped")
        finally:
            if child.poll() is None:
                child.kill()
            child.stdout.close()

    def test_core_shutdown_command_and_missing_pipes(self):
        import io
        import json
        from launcher import serve_core
        out = io.StringIO()
        self.assertEqual(serve_core(io.StringIO("ping\nshutdown\nignored\n"), out), 0)
        events = [json.loads(line)["event"] for line in out.getvalue().splitlines()]
        self.assertEqual(events, ["ready", "stopped"])
        from unittest.mock import patch
        with patch("sys.stdin", None):
            self.assertEqual(serve_core(None, out), 2)


if __name__ == "__main__":
    unittest.main()
