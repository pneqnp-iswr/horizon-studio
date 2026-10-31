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

    def test_a_page_load_burst_is_never_refused(self):
        # A page load opens one connection per script and icon (the handler speaks HTTP/1.0), up to six at a
        # time. They wait in the listen backlog until the server accepts them; with socketserver's default of 5,
        # Windows refused the sixth, a script failed to load and the desktop editor started without its bridge.
        import socket
        import threading
        from studio import WEB_SCRIPTS
        script = sorted(WEB_SCRIPTS)[0]
        for exclusive in (False, True):  # the browser launcher and the desktop core
            with self.subTest(exclusive=exclusive):
                server = start_server(smoke_test=not exclusive, exclusive=exclusive)
                port, sockets, serving = server.server_port, [], None
                try:
                    # The server is not accepting yet, so every connection has to fit in the backlog.
                    for _ in range(32):
                        sockets.append(socket.create_connection(("127.0.0.1", port), timeout=5))
                    serving = threading.Thread(target=server.serve_forever, daemon=True)
                    serving.start()
                    for conn in sockets:
                        conn.sendall(f"GET /{script} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode())
                    for conn in sockets:
                        with conn.makefile("rb") as reply:
                            self.assertIn(b" 200 ", reply.readline())
                finally:
                    for conn in sockets:
                        conn.close()
                    if serving:
                        server.shutdown()
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
            # The token travels in the handshake only; the desktop core refuses to hand it out.
            self.assertRegex(ready["token"], r"^[A-Za-z0-9_-]{32,128}$")
            import urllib.error
            with self.assertRaises(urllib.error.HTTPError) as refused:
                urllib.request.urlopen(ready["url"] + "api/session", timeout=10)
            self.assertEqual(refused.exception.code, 403)
            def post(headers):
                request = urllib.request.Request(ready["url"] + "api/preview", data=b"{}", method="POST",
                                                 headers={"Content-Type": "application/json", **headers})
                try:
                    with urllib.request.urlopen(request, timeout=10) as response:
                        return response.status
                except urllib.error.HTTPError as error:
                    return error.code
            self.assertEqual(post({}), 403, "no token, no API")
            self.assertEqual(post({"X-Studio-Token": ready["token"]}), 400, "authorized; the empty request is then invalid")
            with urllib.request.urlopen(ready["url"], timeout=10) as response:
                self.assertIn(b"Horizon Studio", response.read())
            child.stdin.close()  # what happens when the shell exits or crashes
            self.assertEqual(child.wait(timeout=15), 0)
            self.assertEqual(json.loads(child.stdout.readline())["event"], "stopped")
        finally:
            if child.poll() is None:
                child.kill()
            child.stdout.close()

    def test_the_desktop_core_port_cannot_be_shared(self):
        """S1: on Windows SO_REUSEADDR would let another process bind the core's port."""
        import socket
        from launcher import ExclusiveHTTPServer, start_server
        server = start_server(exclusive=True)
        try:
            self.assertIsInstance(server, ExclusiveHTTPServer)
            self.assertFalse(server.allow_reuse_address)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.assertTrue(server.socket.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE))
            intruder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                intruder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                with self.assertRaises(OSError):
                    intruder.bind(server.server_address)
            finally:
                intruder.close()
        finally:
            server.server_close()

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
