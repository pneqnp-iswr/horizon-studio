"""Roadmap source of truth: validation rules, derived states and generated outputs."""
import copy
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import render_branding, roadmap  # noqa: E402
from scripts.pixelart import Canvas, png_scanlines  # noqa: E402

DATA = json.loads((ROOT / "docs" / "roadmap" / "roadmap.json").read_text(encoding="utf-8"))
SVG_NS = "{http://www.w3.org/2000/svg}"


def milestone(data, mid):
    return next(m for m in data["milestones"] if m["id"] == mid)


class RoadmapValidationTests(unittest.TestCase):
    def assert_rejected(self, mutate, expected):
        data = copy.deepcopy(DATA)
        mutate(data)
        problems = roadmap.validate(data)
        self.assertTrue(any(expected in p for p in problems), problems)

    def test_repository_roadmap_is_valid(self):
        self.assertEqual(roadmap.validate(DATA), [])

    def test_rejects_missing_and_duplicate_identifiers(self):
        self.assert_rejected(lambda d: d["milestones"][0].pop("id"), "needs an id like HS-001")
        self.assert_rejected(lambda d: d["milestones"].append(copy.deepcopy(d["milestones"][0])),
                             "Duplicate milestone HS-001")
        self.assert_rejected(lambda d: d["phases"].append(copy.deepcopy(d["phases"][0])), "Duplicate phase F0")

    def test_rejects_unsupported_status_values(self):
        self.assert_rejected(lambda d: milestone(d, "HS-003").update(status="finished"), "unsupported status")
        self.assert_rejected(lambda d: d["verification"][0].update(status="green"), "unsupported status")

    def test_rejects_references_to_missing_entries(self):
        self.assert_rejected(lambda d: milestone(d, "HS-010").update(depends_on=["HS-999"]), "unknown milestone")
        self.assert_rejected(lambda d: milestone(d, "HS-010").update(phase="F9"), "unknown phase")
        self.assert_rejected(lambda d: d.update(active_milestone="HS-999"), "not a milestone")
        self.assert_rejected(lambda d: d.update(next_milestones=["HS-001"]), "must be a planned milestone")

    def test_rejects_contradictory_states(self):
        def done_on_planned(d):
            milestone(d, "HS-017").update(status="planned")
            milestone(d, "HS-018").update(status="done", evidence=[{"level": "unit", "ref": "x", "url": "docs/PROJECT_FORMAT.md"}])
        self.assert_rejected(done_on_planned, "dependency HS-017 is planned")
        def started_on_planned(d):
            milestone(d, "HS-017").update(status="planned")
            milestone(d, "HS-018").update(status="in_progress")
        self.assert_rejected(started_on_planned, "has not started")
        self.assert_rejected(lambda d: d.update(active_milestone="HS-005"), "is not in_progress")
        self.assert_rejected(lambda d: milestone(d, "HS-009").update(status="in_progress"),
                             "in progress outside the current phase")
        def skip_a_level(d):
            d["verification"][3].update(status="blocked", evidence=[])
            d["verification"][4].update(status="verified", evidence=[{"ref": "x", "url": "docs/GAME_CONTENT_SMOKE.md"}])
        self.assert_rejected(skip_a_level, "lower level is not")

    def test_rejects_invalid_or_missing_evidence(self):
        self.assert_rejected(lambda d: milestone(d, "HS-003").update(evidence=[]), "without evidence")
        self.assert_rejected(lambda d: milestone(d, "HS-003").update(
            evidence=[{"level": "docs", "ref": "x", "url": "docs/PROJECT_FORMAT.md"}]), "documentation-only")
        self.assert_rejected(lambda d: milestone(d, "HS-003")["evidence"][0].update(url="https://example.com/x"),
                             "must link into")
        self.assert_rejected(lambda d: milestone(d, "HS-003")["evidence"][0].update(url="docs/NOPE.md"),
                             "missing file")
        self.assert_rejected(lambda d: milestone(d, "HS-003")["evidence"][0].update(level="vibes"),
                             "unsupported level")
        self.assert_rejected(lambda d: milestone(d, "HS-005").update(status="partial"), "does not say what is missing")
        self.assert_rejected(lambda d: milestone(d, "HS-002").pop("blocker"), "without a blocker")
        self.assert_rejected(lambda d: d["verification"][0].update(evidence=[]), "verified without evidence")

    def test_phase_states_are_derived_from_milestones(self):
        states = {p["id"]: roadmap.phase_status(DATA, p["id"]) for p in DATA["phases"]}
        self.assertEqual(states["F0"], "partial")  # HS-002 is blocked
        self.assertEqual(states[DATA["current_phase"]], "in_progress")
        data = copy.deepcopy(DATA)
        milestone(data, "HS-002").update(status="done", blocker="")
        milestone(data, "HS-002")["evidence"].append(
            {"level": "game-load", "ref": "x", "url": "docs/GAME_CONTENT_SMOKE.md"})
        self.assertEqual(roadmap.phase_status(data, "F0"), "done")


class RoadmapGovernanceTests(unittest.TestCase):
    """roadmap/2: every milestone carries scope, deliverable, acceptance, engine requirements,
    a validation target and a design reference, and the graph stays consistent."""

    def assert_rejected(self, mutate, expected):
        data = copy.deepcopy(DATA)
        mutate(data)
        problems = roadmap.validate(data)
        self.assertTrue(any(expected in p for p in problems), problems)

    def test_file_is_in_canonical_form(self):
        raw = (ROOT / "docs" / "roadmap" / "roadmap.json").read_text(encoding="utf-8")
        self.assertEqual(raw, roadmap.dumps(json.loads(raw)))

    def test_rejects_missing_governance_fields(self):
        for field, expected in (("summary_ru", "needs summary_ru"), ("deliverable", "needs deliverable")):
            self.assert_rejected(lambda d, f=field: milestone(d, "HS-020").pop(f), expected)
        self.assert_rejected(lambda d: milestone(d, "HS-020").update(acceptance=[]), "needs acceptance criteria")
        self.assert_rejected(lambda d: milestone(d, "HS-020").update(validation_target="docs"), "validation_target")
        self.assert_rejected(lambda d: milestone(d, "HS-020").update(design_ref="docs/NOPE.md"), "design_ref")
        self.assert_rejected(lambda d: milestone(d, "PC-001").update(track="studio"), "track must be pixelchat")

    def test_rejects_dependency_cycles(self):
        self.assert_rejected(lambda d: milestone(d, "HS-005").update(depends_on=["HS-020"]), "Dependency cycle")

    def test_rejects_unknown_engine_requirements(self):
        self.assert_rejected(lambda d: milestone(d, "HS-025").update(engine_requirements=["vfx.magic"]),
                             "unknown engine requirement 'vfx.magic'")

    def test_an_authoring_ui_is_not_a_runtime(self):
        """A milestone that needs a missing engine contract cannot be done, whatever its evidence."""
        def finish(d):
            milestone(d, "HS-029").update(status="done", depends_on=[], evidence=[
                {"level": "browser-e2e", "ref": "timeline panel", "url": "docs/BROWSER_E2E.md"}])
        self.assert_rejected(finish, "HS-029 is done but needs entity.animation_runtime")

    def test_done_needs_evidence_at_its_validation_target(self):
        self.assert_rejected(lambda d: milestone(d, "HS-007").update(validation_target="desktop-e2e"),
                             "HS-007 is done without desktop-e2e evidence")

    def test_showcase_levels_climb_in_order(self):
        self.assert_rejected(lambda d: d["showcases"][0]["levels"][2].update(status="verified"),
                             "a level cannot be verified before the level below it")
        self.assert_rejected(lambda d: d["showcases"][0]["milestones"].append("HS-999"), "unknown milestone HS-999")

    def test_engine_contracts_are_documented(self):
        self.assert_rejected(lambda d: d["engine_contracts"][0].update(status="maybe"), "status must be one of")
        self.assert_rejected(lambda d: d["engine_contracts"][0].pop("source"), "needs source")

    def test_v1_documents_upgrade_but_never_pass_without_governance(self):
        old = {"schema": roadmap.PREVIOUS_SCHEMA, **{k: copy.deepcopy(v) for k, v in DATA.items() if k != "schema"}}
        for item in old["milestones"]:
            for field in ("track", "summary", "summary_ru", "deliverable", "deliverable_ru", "acceptance",
                          "engine_requirements", "validation_target", "design_ref"):
                item.pop(field, None)
        upgraded = roadmap.upgrade(old)
        self.assertEqual(upgraded["schema"], roadmap.SCHEMA)
        self.assertEqual({m["id"] for m in upgraded["milestones"]}, {m["id"] for m in DATA["milestones"]})
        self.assertTrue(any("needs acceptance criteria" in p for p in roadmap.validate(upgraded)))
        self.assertEqual(roadmap.upgrade(DATA), DATA)

    def test_every_creative_platform_family_is_traceable(self):
        ids = {m["id"]: m for m in DATA["milestones"]}
        families = {
            "AI Creator": ["HS-020", "HS-021", "HS-022"], "Live preview": ["HS-023", "HS-024", "HS-002"],
            "VFX Studio": ["HS-025", "HS-026", "HS-013", "HS-027"], "Model and animation": ["HS-028", "HS-009", "HS-029"],
            "Entity and boss": ["HS-030", "HS-014", "HS-031", "HS-032"], "World and physics": ["HS-016", "HS-015", "HS-032"],
            "PixelChat": ["PC-001", "PC-002", "PC-003", "PC-004", "PC-005"], "Ecosystem": ["HS-017", "HS-034", "HS-018"],
        }
        for family, members in families.items():
            for mid in members:
                self.assertIn(mid, ids, f"{family}: {mid}")
        self.assertEqual(ids["HS-030"]["engine_requirements"], ["entity.custom"], "custom entities stay engine-dependent")
        self.assertTrue(all(ids[m]["track"] == "pixelchat" for m in families["PixelChat"]))
        titan = DATA["showcases"][0]
        self.assertEqual((titan["id"], titan["name"], len(titan["levels"]), len(titan["sequence"])), ("SC-001", "Crystal Titan", 5, 8))
        self.assertTrue(all(level["status"] == "planned" for level in titan["levels"]))

    def test_phase_progress_ignores_the_experimental_track(self):
        f7 = roadmap.milestones_of(DATA, "F7")
        self.assertTrue(f7 and all(m["track"] == "studio" for m in f7))
        self.assertEqual(len(roadmap.milestones_of(DATA, "F7", "pixelchat")), 5)


class ReleaseDataTests(unittest.TestCase):
    RELEASES = json.loads((ROOT / "docs" / "releases" / "releases.json").read_text(encoding="utf-8"))
    VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    def problems(self, mutate):
        releases = copy.deepcopy(self.RELEASES)
        mutate(releases["releases"][0])
        return roadmap.validate_releases(DATA, releases, self.VERSION)

    def test_repository_release_data_is_valid(self):
        self.assertEqual(roadmap.validate_releases(DATA, self.RELEASES, self.VERSION), [])

    def test_rejects_development_features_claimed_for_an_older_release(self):
        found = self.problems(lambda r: r["capabilities"].append({"en": "x", "ru": "x", "milestone": "HS-005"}))
        self.assertTrue(any("landed after PR #0" in p for p in found), found)

    def test_rejects_inconsistent_release_metadata(self):
        for mutate, expected in (
                (lambda r: r.update(tag="v9.9.9"), "tag must be"),
                (lambda r: r["executable"].update(name="HorizonStudio-0.5.0-Windows-x64.exe"), "executable name"),
                (lambda r: r["executable"].update(sha256="xyz"), "SHA-256"),
                (lambda r: r.update(version="99.0.0", tag="v99.0.0"), "newer than VERSION"),
                (lambda r: r.update(commit="63a313f"), "full SHA")):
            with self.subTest(expected):
                self.assertTrue(any(expected in p for p in self.problems(mutate)))

    def test_panel_lists_newer_work_as_not_released(self):
        section = roadmap.release_section(DATA, self.RELEASES, "en")
        latest = roadmap.latest_release(self.RELEASES)
        self.assertIn(latest["executable"]["sha256"], section)
        self.assertIn(f"/releases/download/{latest['tag']}/{latest['executable']['name']}", section)
        if latest["last_pr"] < 7:
            self.assertIn("HS-005", section.split("not in this executable", 1)[1])


class GeneratedOutputTests(unittest.TestCase):
    def test_committed_roadmap_outputs_are_current(self):
        self.assertEqual(roadmap.main(["--check"]), 0)

    def test_committed_branding_is_current(self):
        self.assertEqual(render_branding.main(["--check"]), 0)

    def test_svgs_are_static_crisp_and_self_contained(self):
        files = list((ROOT / "assets" / "branding").glob("*.svg")) + list((ROOT / "assets" / "roadmap").glob("*.svg"))
        self.assertEqual(len(files), 5)  # banner, mark, wordmark, two roadmap images
        for path in files:
            with self.subTest(path.name):
                raw = path.read_text(encoding="utf-8")
                tree = ET.fromstring(raw)
                self.assertEqual(tree.tag, f"{SVG_NS}svg")
                self.assertEqual(tree.get("shape-rendering"), "crispEdges")
                self.assertTrue(tree.find(f"{SVG_NS}title").text.strip())
                self.assertTrue(tree.find(f"{SVG_NS}desc").text.strip())
                for banned in ("<script", "href=", "<image", "<foreignObject", "@import", "url("):
                    self.assertNotIn(banned, raw)
                self.assertLess(len(raw.encode("utf-8")), 200_000)

    def test_png_fallbacks_match_their_svgs(self):
        for name, (canvas, scale, _, _) in render_branding.outputs().items():
            with self.subTest(name):
                width, height, lines = png_scanlines((ROOT / "assets" / "branding" / f"{name}.png").read_bytes())
                self.assertEqual((width, height), (canvas.width * scale, canvas.height * scale))
                self.assertEqual(lines, canvas.png_scanlines(scale))

    def test_readmes_embed_banner_and_roadmap(self):
        for page in ("README.md", "README.ru.md"):
            text = (ROOT / page).read_text(encoding="utf-8")
            with self.subTest(page):
                self.assertTrue(text.startswith('<p align="center">\n  <img src="assets/branding/horizon-studio-banner.svg"'))
                self.assertIn("assets/roadmap/roadmap-overview.svg", text)
                self.assertIn("assets/roadmap/current-phase.svg", text)
                for line in text.splitlines():
                    if 'src="docs/' in line or 'src="assets/' in line:
                        target = line.split('src="', 1)[1].split('"', 1)[0]
                        self.assertTrue((ROOT / target).is_file(), target)


class PixelArtTests(unittest.TestCase):
    def test_rectangles_cover_exactly_the_painted_pixels(self):
        canvas = Canvas(9, 7)
        canvas.rect(1, 1, 4, 3, "#112233")
        canvas.rect(5, 1, 2, 3, "#445566")
        canvas.set(8, 6, "#112233")
        painted = {(x, y) for y in range(7) for x in range(9) if canvas.px[y][x]}
        covered = set()
        for color, rects in canvas.rectangles().items():
            for x, y, w, h in rects:
                for yy in range(y, y + h):
                    for xx in range(x, x + w):
                        self.assertEqual(canvas.px[yy][xx], color)
                        self.assertNotIn((xx, yy), covered)
                        covered.add((xx, yy))
        self.assertEqual(covered, painted)
        self.assertEqual(len(canvas.rectangles()["#112233"]), 2)

    def test_text_rejects_unknown_glyphs(self):
        with self.assertRaises(ValueError):
            Canvas(20, 10).text(0, 0, "€", "#ffffff")


class TestInventoryTests(unittest.TestCase):
    def test_documented_e2e_inventory_is_current(self):
        import shutil
        if shutil.which("node") is None:
            self.skipTest("node is not installed")
        from scripts import test_inventory
        self.assertEqual(test_inventory.main(["--check"]), 0)
        names = [s["name"] for s in test_inventory.e2e_scenarios()]
        self.assertEqual(len(names), len(set(names)), "scenario names must be unique")


if __name__ == "__main__":
    unittest.main()
