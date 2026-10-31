"""HS-025: studio.vfx/1 effects in the core: validation, determinism and the canonical project."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from studio_core import capabilities, vfx
from studio_core.graph import AssetGraph
from studio_core.migrate import from_editor_state, to_editor_state, to_generator_request, upgrade
from studio_core.project_schema import ProjectFormatError, validate_document

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "vfx_impact_spark.json"
OFFICIAL_RUBY = "ee3e1c878ea41fbf710f749896bfdb92b23b18e21e67b016b57b95b96a8797e2"
UID = "11111111-1111-4111-8111-111111111111"


def with_effect(**changes):
    effect = vfx.impact_spark()
    for path, value in changes.items():
        target = effect
        keys = path.split("__")
        for key in keys[:-1]:
            target = target[int(key)] if key.isdigit() else target[key]
        last = keys[-1]
        target[int(last) if last.isdigit() else last] = value
    return effect


class VfxModelTests(unittest.TestCase):
    def test_the_preset_is_valid_and_the_same_seed_gives_the_same_trajectories(self):
        effect = vfx.impact_spark()
        self.assertEqual(vfx.validate(effect), [])
        self.assertEqual(vfx.simulate(effect, 0.2), vfx.simulate(copy.deepcopy(effect), 0.2))
        other = with_effect(seed=7)
        self.assertNotEqual([p["position"] for p in vfx.simulate(other, 0.2)],
                            [p["position"] for p in vfx.simulate(effect, 0.2)])
        # Adding an emitter never changes the particles of the others (one random stream per emitter).
        more = copy.deepcopy(effect)
        more["emitters"].append(copy.deepcopy(more["emitters"][0]) | {"id": "extra"})
        sparks = [p for p in vfx.simulate(more, 0.2) if p["emitter"] == 0]
        self.assertEqual(sparks, [p for p in vfx.simulate(effect, 0.2) if p["emitter"] == 0])

    def test_the_editor_fixture_is_current(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["effect"], vfx.impact_spark())
        for time, alive in fixture["alive"].items():
            self.assertEqual(len(vfx.simulate(fixture["effect"], float(time))), alive)
        # The fixture was generated on Linux; other platforms' math libraries may round the last bit
        # differently (Windows CI does), so values agree to 1e-12 rather than bit for bit.
        for time, frame in fixture["frames"].items():
            now = vfx.simulate(fixture["effect"], float(time))
            self.assertEqual(len(now), len(frame))
            for p, q in zip(now, frame):
                self.assertEqual(p["emitter"], q["emitter"])
                for key in ("position", "trail"):
                    for a, b in zip(p[key], q[key]):
                        self.assertAlmostEqual(a, b, delta=1e-12)
                self.assertAlmostEqual(p["size"], q["size"], delta=1e-12)
                self.assertAlmostEqual(p["alpha"], q["alpha"], delta=1e-12)
                self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(p["color"], q["color"])))

    def test_motion_follows_gravity_and_drag_and_loops_wrap(self):
        effect = vfx.impact_spark()
        early = {p["emitter"]: p for p in vfx.simulate(effect, 0.0)}
        self.assertEqual(early[1]["position"], [0, 0, 0], "the flash sits at the impact point")
        late = [p for p in vfx.simulate(effect, 0.45) if p["emitter"] == 0]
        self.assertTrue(late and all(p["size"] < 0.1 for p in late), "sparks shrink over their life")
        self.assertEqual(vfx.simulate(effect, 2.0), [], "a one-shot effect ends")
        looping = with_effect(loop=True)
        wrapped, first = vfx.simulate(looping, 0.2 + looping["duration"]), vfx.simulate(looping, 0.2)
        self.assertEqual(len(wrapped), len(first))
        for p, q in zip(wrapped, first):  # one period later, up to the rounding of t mod duration
            for a, b in zip(p["position"], q["position"]):
                self.assertAlmostEqual(a, b, places=9)

    def test_validation_names_each_problem(self):
        cases = {
            "COUNT": with_effect(emitters__0__bursts__0__count=9999),
            "ORDER": with_effect(emitters__0__speed=[8, 2]),
            "COLOR": with_effect(emitters__0__color__0__1="orange"),
            "KEY_START": with_effect(emitters__0__size__0__0=0.2),
            "RANGE": with_effect(duration=0),
            "SEED": with_effect(seed=-1),
            "SCHEMA": with_effect(schema="studio.vfx/2"),
            "BLEND": with_effect(emitters__0__blend="screen"),
            "AXIS": with_effect(emitters__0__direction__axis=[0, 0, 0]),
        }
        for code, effect in cases.items():
            with self.subTest(code):
                self.assertIn(code, [p["code"] for p in vfx.validate(effect)])
        budget = vfx.impact_spark()
        budget["emitters"] = [copy.deepcopy(budget["emitters"][0]) | {"id": f"e{i}"} for i in range(5)]
        for emitter in budget["emitters"]:
            emitter["bursts"] = [{"time": 0, "count": 500}]
        self.assertIn("BUDGET", [p["code"] for p in vfx.validate(budget)])
        twins = vfx.impact_spark()
        twins["emitters"][1]["id"] = "sparks"
        self.assertIn("DUPLICATE", [p["code"] for p in vfx.validate(twins)])


class VfxProjectTests(unittest.TestCase):
    def setUp(self):
        self.doc = upgrade(json.loads((ROOT / "examples" / "ruby_demo.hstudio.json").read_text(encoding="utf-8")))
        state = to_editor_state(self.doc)
        state["effects"] = [{"id": "impact_spark", "uid": UID, **vfx.impact_spark()}]
        self.with_effect = from_editor_state(state)

    def test_effects_round_trip_through_the_canonical_project(self):
        effect = next(o for o in self.with_effect["objects"] if o["kind"] == "vfx")
        self.assertEqual((effect["uid"], effect["id"]), (UID, "impact_spark"))
        self.assertEqual(effect["props"], vfx.impact_spark())
        back = to_editor_state(self.with_effect)
        self.assertEqual(back["effects"], [{"id": "impact_spark", "uid": UID, **vfx.impact_spark()}])
        self.assertNotIn("effects", to_editor_state(self.doc), "projects without effects keep their editor shape")

    def test_effects_are_never_exported_and_never_block_an_export(self):
        from studio import hmod_zip
        request = to_generator_request(self.with_effect)
        self.assertNotIn("effects", request)
        self.assertEqual(hashlib.sha256(hmod_zip(request)).hexdigest(), OFFICIAL_RUBY)
        self.assertEqual(capabilities.check(self.with_effect)["diagnostics"], [])
        codes = [d["code"] for d in AssetGraph(self.with_effect).diagnostics()]
        self.assertEqual(codes, ["VFX_STUDIO_ONLY"])

    def test_invalid_effects_are_reported_and_malformed_ones_refused(self):
        broken = copy.deepcopy(self.with_effect)
        effect = next(o for o in broken["objects"] if o["kind"] == "vfx")
        effect["props"]["emitters"][0]["bursts"][0]["count"] = 0
        self.assertIn("VFX_COUNT", [d["code"] for d in AssetGraph(broken).diagnostics()])
        effect["props"]["schema"] = "something/1"
        with self.assertRaises(ProjectFormatError):
            validate_document(broken)


if __name__ == "__main__":
    unittest.main()
