"""The in-app development journey and the editor's capability check (HS-008)."""
import http.client
import json
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import roadmap  # noqa: E402
from security.request_policy import session_token  # noqa: E402
from studio import Handler, ThreadingHTTPServer  # noqa: E402
from studio_core.capabilities import load_registry  # noqa: E402
from studio_core.journey import phase_status, view  # noqa: E402

DEMO_STATE = {
    "metadata": {"id": "ruby_demo", "name": "Ruby Demo", "version": "0.1.0", "author": "A", "description": ""},
    "blocks": [{"id": "ruby_block", "name": "Block of Ruby", "template": "minecraft:iron_block", "light": 3}],
    "items": [{"id": "ruby", "name": "Ruby", "template": "minecraft:diamond"}],
    "recipes": [{"id": "ruby_block", "type": "shaped", "result": "@ruby_block", "count": 1, "grid": ["@ruby"] * 9}],
    "structures": [], "source_overrides": {},
}


class JourneyViewTests(unittest.TestCase):
    def test_phase_status_matches_the_roadmap_generator(self):
        data = json.loads((ROOT / "docs" / "roadmap" / "roadmap.json").read_text(encoding="utf-8"))
        for phase in data["phases"]:
            self.assertEqual(phase_status(data, phase["id"]), roadmap.phase_status(data, phase["id"]), phase["id"])

    def test_view_separates_the_plan_from_this_build(self):
        result = view()
        self.assertEqual(result["schema"], "horizon-studio.journey/1")
        self.assertEqual(len([p for p in result["phases"] if p["status"] == "in_progress"]), 1)
        self.assertEqual(result["active_milestone"]["status"], "in_progress")
        groups = result["build"]["groups"]
        registry = load_registry()
        profile = next(p for p in registry["profiles"] if p["revision"] == registry["default"])
        self.assertEqual(sum(len(g) for g in groups.values()), len(profile["capabilities"]))
        for status, entries in groups.items():
            for entry in entries:
                self.assertEqual(profile["capabilities"][entry["capability"]]["status"], status)
        self.assertNotIn("milestones", result, "only the summary reaches the editor")


class JourneyHttpTests(unittest.TestCase):
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

    def request(self, method, path, payload=None, token=True):
        con = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Studio-Token"] = session_token(self.server)
        con.request(method, path, body=None if payload is None else json.dumps(payload), headers=headers)
        response = con.getresponse()
        result = response.status, response.read()
        con.close()
        return result

    def test_journey_endpoint(self):
        status, raw = self.request("GET", "/api/journey")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["build"]["revision"], load_registry()["default"])

    def test_capability_check_of_the_editor_state(self):
        status, raw = self.request("POST", "/api/capabilities/check", DEMO_STATE)
        self.assertEqual(status, 200)
        result = json.loads(raw)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(set(result["requirements"]),
                         {"content.block", "content.item", "content.lang", "content.loot_table", "content.recipe"})
        self.assertEqual(result["profile"]["content_api"], "0.2")

    def test_capability_check_needs_the_session_token_and_a_valid_project(self):
        self.assertEqual(self.request("POST", "/api/capabilities/check", DEMO_STATE, token=False)[0], 403)
        # Mod ID rules belong to the export, which reports them itself; a broken document is a 400 here.
        status, raw = self.request("POST", "/api/capabilities/check", {**DEMO_STATE, "blocks": "not a list"})
        self.assertEqual(status, 400, raw)

    def test_every_bundled_asset_is_served(self):
        from studio import BUNDLED_FILES
        for name in BUNDLED_FILES:
            if name.startswith("assets/"):
                with self.subTest(name):
                    self.assertEqual(self.request("GET", "/" + name, token=False)[0], 200)


if __name__ == "__main__":
    unittest.main()
