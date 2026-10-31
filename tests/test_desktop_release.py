"""Desktop release candidates (scripts/desktop_release.py): honest manifests, verified assets, no publishing."""
import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import desktop_release as dr
from scripts.release import ReleaseError

COMMIT = "a" * 40
GATES = {gate: "success" for gate in dr.BUILD_GATES}
UNSIGNED = {"HorizonStudio-setup.exe": {"status": "NotSigned"}, "HorizonStudio.exe": {"status": "NotSigned"},
            "core/horizon-studio-core.exe": {"status": "NotSigned"}}


def metrics(label, ok=True, test_build=False):
    return {"label": label, "ok": ok, "memory": {"total_rss_mb": 350.0},
            "report": {"ok": ok, "shell": {"test_build": test_build}, "window": {"width": 1280, "height": 800},
                       "timings_ms": {"editor_ready": 950, "core_stop": 120}}}


class Candidate:
    def __init__(self, folder: Path, layout=("HorizonStudio.exe", "core/horizon-studio-core.exe", "core/_internal/x.pyd")):
        self.dist = folder / "dist"
        self.smoke = folder / "smoke"
        self.dist.mkdir()
        self.smoke.mkdir()
        self.installer = self.dist / "HorizonStudio-setup.exe"
        self.installer.write_bytes(b"MZ installer")
        self.zip = self.dist / "HorizonStudio-portable.zip"
        with zipfile.ZipFile(self.zip, "w") as archive:
            for name in layout:
                archive.writestr(f"HorizonStudio-portable/{name}", b"MZ" + name.encode())
        for label in ("portable-cold-1280x800", "installed-1280x800"):
            (self.smoke / f"{label}.metrics.json").write_text(json.dumps(metrics(label)), encoding="utf-8")
        self.signing = folder / "signing.json"
        self.signing.write_text(json.dumps(UNSIGNED), encoding="utf-8")

    def manifest(self, gates=GATES, parity=None):
        return dr.build_manifest("0.7.0", COMMIT, self.installer, self.zip, gates, dr.smoke_results(self.smoke),
                                 dr.signing_status(json.loads(self.signing.read_text()), list(UNSIGNED)), parity or {})

    def write(self, manifest):
        path = self.dist / "desktop-manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        names = [a["name"] for a in manifest["artifacts"]] + [path.name]
        (self.dist / "SHA256SUMS.txt").write_text(dr.checksums(self.dist, names), encoding="ascii", newline="\n")
        return path


class DesktopReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = Candidate(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_candidate_records_what_the_run_proved_and_is_not_release_ready(self):
        manifest = self.c.manifest(parity={"desktop-e2e": True})
        self.assertEqual(manifest["channel"], "preview")
        self.assertEqual(manifest["build"], "preview-aaaaaaa")
        self.assertFalse(manifest["release_ready"], "release-pipeline, signing decision and migration note are missing")
        self.assertTrue(manifest["parity"]["desktop-e2e"]["passed"])
        self.assertEqual(manifest["signing"]["overall"], "unsigned")
        portable = next(a for a in manifest["artifacts"] if a["kind"] == "portable-zip")
        self.assertIn("not a single-file executable", portable["note"])
        self.assertEqual(portable["contents"]["folder"], "HorizonStudio-portable")
        self.assertEqual([s["label"] for s in manifest["smoke"]], ["installed-1280x800", "portable-cold-1280x800"])
        self.assertTrue(any("SmartScreen" in line for line in manifest["limitations"]))
        path = self.c.write(manifest)
        self.assertEqual(dr.verify(self.c.dist, path), [])

    def test_every_parity_gate_is_needed_before_release_ready(self):
        everything = {gate: True for gate in dr.PARITY_GATES}
        self.assertTrue(self.c.manifest(parity=everything)["release_ready"])
        for gate in dr.PARITY_GATES:
            with self.subTest(gate):
                self.assertFalse(self.c.manifest(parity={**everything, gate: False})["release_ready"])
        with self.assertRaises(ReleaseError):
            self.c.manifest(parity={"looks-fine": True})

    def test_failed_or_missing_build_gates_produce_no_manifest(self):
        for gates in ({**GATES, "desktop-e2e": "failure"}, {k: v for k, v in GATES.items() if k != "zip-launch"}, {}):
            with self.assertRaises(ReleaseError):
                self.c.manifest(gates=gates)

    def test_a_test_build_or_a_failed_smoke_run_is_refused(self):
        (self.c.smoke / "x.metrics.json").write_text(json.dumps(metrics("x", test_build=True)), encoding="utf-8")
        with self.assertRaisesRegex(ReleaseError, "test build"):
            dr.smoke_results(self.c.smoke)
        (self.c.smoke / "x.metrics.json").write_text(json.dumps(metrics("x", ok=False)), encoding="utf-8")
        with self.assertRaisesRegex(ReleaseError, "failed"):
            dr.smoke_results(self.c.smoke)

    def test_signing_is_reported_exactly_as_authenticode_says(self):
        self.assertEqual(dr.signing_status(UNSIGNED, list(UNSIGNED))["overall"], "unsigned")
        signed = {name: {"status": "Valid"} for name in UNSIGNED}
        self.assertEqual(dr.signing_status(signed, list(UNSIGNED))["overall"], "signed")
        mixed = {**signed, "HorizonStudio.exe": {"status": "NotSigned"}}
        self.assertEqual(dr.signing_status(mixed, list(UNSIGNED))["overall"], "mixed")
        with self.assertRaises(ReleaseError):
            dr.signing_status({}, list(UNSIGNED))
        # A mixed signature state can never be release ready.
        self.c.signing.write_text(json.dumps(mixed), encoding="utf-8")
        self.assertFalse(self.c.manifest(parity={gate: True for gate in dr.PARITY_GATES})["release_ready"])

    def test_the_portable_zip_must_carry_the_shell_and_its_core(self):
        for layout in (("HorizonStudio.exe",), ("core/horizon-studio-core.exe",)):
            with self.subTest(layout), tempfile.TemporaryDirectory() as other:
                with self.assertRaises(ReleaseError):
                    Candidate(Path(other), layout).manifest()

    def test_verify_catches_tampering_and_false_claims(self):
        path = self.c.write(self.c.manifest())
        self.c.installer.write_bytes(b"MZ something else")
        self.assertTrue(any("differs from the manifest" in p for p in dr.verify(self.c.dist, path)))
        path = self.c.write(self.c.manifest())
        manifest = json.loads(path.read_text())
        manifest["release_ready"] = True
        manifest["signing"]["overall"] = "signed"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        problems = dr.verify(self.c.dist, path)
        self.assertTrue(any("release_ready" in p for p in problems))
        self.assertTrue(any("Signing is claimed" in p for p in problems))
        self.assertTrue(any("desktop-manifest.json differs" in p for p in problems))

    def test_cli_round_trip(self):
        out = self.c.dist / "desktop-manifest.json"
        args = ["manifest", "--version", "0.7.0", "--commit", COMMIT, "--installer", str(self.c.installer),
                "--portable-zip", str(self.c.zip), "--smoke", str(self.c.smoke), "--signing", str(self.c.signing),
                "--out", str(out), "--parity", "desktop-e2e"] + [f"--gate={g}=success" for g in dr.BUILD_GATES]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dr.main(args), 0)
            self.assertEqual(dr.main(["checksums", "--dist", str(self.c.dist), self.c.installer.name, self.c.zip.name, out.name]), 0)
            self.assertEqual(dr.main(["verify", "--dist", str(self.c.dist), "--manifest", str(out)]), 0)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(dr.main(args[:-1] + ["--gate=desktop-e2e=failure"]), 1)

    def test_the_script_cannot_publish(self):
        source = Path(dr.__file__).read_text(encoding="utf-8")
        for forbidden in ("api.github.com", "GITHUB_TOKEN", "urllib.request", "publish("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
