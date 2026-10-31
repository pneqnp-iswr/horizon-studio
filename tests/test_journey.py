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
    """The in-app explorer receives the whole roadmap graph and, apart from it, this build."""

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "docs" / "roadmap" / "roadmap.json").read_text(encoding="utf-8"))
        cls.view = view()

    def test_phase_status_matches_the_roadmap_generator(self):
        for phase in self.data["phases"]:
            self.assertEqual(phase_status(self.data, phase["id"]), roadmap.phase_status(self.data, phase["id"]), phase["id"])

    def test_every_structured_milestone_reaches_the_api(self):
        self.assertEqual(self.view["schema"], "horizon-studio.journey/2")
        self.assertEqual([m["id"] for m in self.view["milestones"]], [m["id"] for m in self.data["milestones"]])
        listed = [mid for phase in self.view["phases"] for mid in phase["milestones"]]
        self.assertEqual(sorted(listed), sorted(m["id"] for m in self.data["milestones"]))
        self.assertEqual([p["id"] for p in self.view["phases"]], [f"F{i}" for i in range(9)])
        for item in self.view["milestones"]:
            for field in ("title", "title_ru", "summary", "summary_ru", "deliverable", "deliverable_ru", "acceptance"):
                self.assertTrue(item[field], f"{item['id']} {field}")

    def test_dependencies_and_dependents_agree(self):
        by_id = {m["id"]: m for m in self.view["milestones"]}
        for item in self.view["milestones"]:
            for dep in item["depends_on"]:
                self.assertIn(item["id"], by_id[dep]["dependents"])
            for user in item["dependents"]:
                self.assertIn(item["id"], by_id[user]["depends_on"])

    def test_statuses_and_active_milestone_come_from_roadmap_json(self):
        source = {m["id"]: m["status"] for m in self.data["milestones"]}
        self.assertEqual({m["id"]: m["status"] for m in self.view["milestones"]}, source)
        self.assertEqual(source["HS-002"], "blocked")
        self.assertEqual(self.view["active_milestone"], self.data["active_milestone"])
        self.assertEqual(self.view["current_phase"], self.data["current_phase"])

    def test_links_are_well_formed_github_links_to_existing_files(self):
        repo = "https://github.com/pneqnp-iswr/horizon-studio"
        for item in self.view["milestones"]:
            for url in [item["design"], *(e["url"] for e in item["evidence"]), *([item["issue"]] if "issue" in item else [])]:
                with self.subTest(item["id"], url=url):
                    self.assertTrue(url.startswith(repo + "/"), url)
                    if "/blob/master/" in url:
                        self.assertTrue((ROOT / url.split("/blob/master/", 1)[1]).is_file(), url)

    def test_the_installed_build_is_not_the_roadmap(self):
        build = self.view["build"]
        self.assertEqual(build["studio_version"], (ROOT / "VERSION").read_text(encoding="utf-8").strip())
        registry = load_registry()
        profile = next(p for p in registry["profiles"] if p["revision"] == registry["default"])
        listed = [c["capability"] for group in build["groups"].values() for c in group]
        self.assertEqual(sorted(listed), sorted(profile["capabilities"]))
        self.assertFalse([c for c in listed if c.startswith(("HS-", "PC-"))])
        for status, entries in build["groups"].items():
            for entry in entries:
                self.assertEqual(profile["capabilities"][entry["capability"]]["status"], status)
        # Roadmap requirements carry their own state; a planned milestone never shows as buildable work.
        states = {r["state"] for m in self.view["milestones"] for r in m["requirements"]}
        self.assertLessEqual(states, {"buildable", "engine", "missing"})

    def test_showcase_and_pixelchat_track_are_present(self):
        self.assertEqual([s["id"] for s in self.view["showcases"]], ["SC-001"])
        pixelchat = [m for m in self.view["milestones"] if m["track"] == "pixelchat"]
        self.assertEqual([m["id"] for m in pixelchat], [f"PC-00{i}" for i in range(1, 6)])
        self.assertTrue(all(m["issue"].endswith("/issues/11") for m in pixelchat))


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
        self.assertEqual(json.loads(raw), json.loads(json.dumps(view())))

    def test_desktop_core_serves_the_same_journey_as_the_browser_server(self):
        """The desktop shell's core (launcher.py --serve) and studio.py answer identically."""
        import os
        import subprocess
        import urllib.request
        child = subprocess.Popen([sys.executable, str(ROOT / "launcher.py"), "--serve"], cwd=ROOT,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                 env={**os.environ, "PYTHONUNBUFFERED": "1"})
        try:
            url = json.loads(child.stdout.readline())["url"]
            with urllib.request.urlopen(url + "api/journey", timeout=10) as response:
                desktop = json.loads(response.read())
            self.assertEqual(desktop, json.loads(self.request("GET", "/api/journey")[1]))
        finally:
            child.stdin.close()
            child.wait(timeout=15)
            child.stdout.close()

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
