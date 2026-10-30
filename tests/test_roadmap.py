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
        self.assert_rejected(lambda d: milestone(d, "HS-010").update(
            status="done", evidence=[{"level": "unit", "ref": "x", "url": "docs/PROJECT_FORMAT.md"}]),
            "dependency HS-008 is planned")
        self.assert_rejected(lambda d: milestone(d, "HS-012").update(status="in_progress"), "has not started")
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


class GeneratedOutputTests(unittest.TestCase):
    def test_committed_roadmap_outputs_are_current(self):
        self.assertEqual(roadmap.main(["--check"]), 0)

    def test_committed_branding_is_current(self):
        self.assertEqual(render_branding.main(["--check"]), 0)

    def test_svgs_are_static_crisp_and_self_contained(self):
        files = list((ROOT / "assets" / "branding").glob("*.svg")) + list((ROOT / "assets" / "roadmap").glob("*.svg"))
        self.assertEqual(len(files), 4)
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


if __name__ == "__main__":
    unittest.main()
