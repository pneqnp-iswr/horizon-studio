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


if __name__ == "__main__":
    unittest.main()
