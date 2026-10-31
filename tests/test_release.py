"""Release gates: notes, manifest, bundling and strictly idempotent publication (API double)."""
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import release  # noqa: E402
from scripts.release import ReleaseError  # noqa: E402

COMMIT = "a" * 40
OTHER = "b" * 40
VERSION = "9.8.7"
NOTES = f"# Horizon Studio {VERSION} — Test\n\nDownload `HorizonStudio-{VERSION}-Windows-x64.exe`.\n"
SMOKE = {"ok": True, "version": VERSION, "checks": {"shutdown": "clean"}}
GATES = {"python": "success", "node": "success", "browser-e2e": "success", "official-check": "success"}


class FakeGitHub:
    """In-memory GitHub releases/tags with the behaviour publish() relies on."""

    def __init__(self):
        self.releases, self.tags, self.blobs, self.writes = [], {}, {}, []
        self.next_id = 1
        self.corrupt_uploads = False  # same size, different bytes

    def find_release(self, tag):
        return next((json.loads(json.dumps(r)) for r in self.releases if r["tag_name"] == tag), None)

    def tag_commit(self, tag):
        return self.tags.get(tag)

    def create_draft(self, tag, commit, name, body, prerelease):
        self.writes.append(("create", tag))
        rel = {"id": self.next_id, "tag_name": tag, "target_commitish": commit, "name": name, "body": body,
               "draft": True, "prerelease": prerelease, "assets": [], "upload_url": "u{?name}",
               "html_url": f"https://github.com/o/r/releases/tag/{tag}"}
        self.next_id += 1
        self.releases.append(rel)
        return json.loads(json.dumps(rel))

    def _store(self, rel, name, data):
        url = f"blob://{rel['id']}/{name}"
        self.blobs[url] = data
        rel["assets"].append({"name": name, "size": len(data), "state": "uploaded", "url": url,
                              "browser_download_url": url,
                              "digest": "sha256:" + hashlib.sha256(data).hexdigest()})

    def upload(self, rel, path):
        self.writes.append(("upload", path.name))
        target = next(r for r in self.releases if r["id"] == rel["id"])
        data = path.read_bytes()
        self._store(target, path.name, data[:-1] + bytes([data[-1] ^ 1]) if self.corrupt_uploads else data)

    def update(self, rel, **fields):
        self.writes.append(("update", tuple(sorted(fields))))
        target = next(r for r in self.releases if r["id"] == rel["id"])
        target.update(fields)
        if fields.get("draft") is False:
            self.tags.setdefault(target["tag_name"], target["target_commitish"])
        return target

    def release(self, rid):
        return json.loads(json.dumps(next(r for r in self.releases if r["id"] == rid)))

    def asset_bytes(self, asset):
        return self.blobs[asset["url"]]

    def asset_sha256(self, asset):
        return asset["digest"].split(":", 1)[1]

    def reachable(self, url):
        return url in self.blobs


class Build:
    def __init__(self, exe_bytes=b"MZ fake windows executable"):
        self.dir = tempfile.TemporaryDirectory()
        self.dist = Path(self.dir.name)
        exe = self.dist / release.exe_name(VERSION)
        exe.write_bytes(exe_bytes)
        manifest = release.build_manifest(VERSION, exe, COMMIT, f"v{VERSION}", GATES, SMOKE)
        (self.dist / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.dist / "SHA256SUMS.txt").write_text(
            release.checksums(self.dist, [exe.name, "build-manifest.json"]), encoding="ascii")

    def close(self):
        self.dir.cleanup()


def desktop_build(build, ready=True):
    """Adds a desktop installer, portable ZIP and manifest (as desktop.yml's release channel makes them)."""
    import zipfile
    from scripts import desktop_release as dr
    setup, portable, _ = release.desktop_names(VERSION)
    (build.dist / setup).write_bytes(b"MZ nsis installer")
    with zipfile.ZipFile(build.dist / portable, "w") as archive:
        for name in ("HorizonStudio.exe", "core/horizon-studio-core.exe"):
            archive.writestr(f"HorizonStudio-{VERSION}/{name}", b"MZ" + name.encode())
    smoke = build.dist / "smoke"
    smoke.mkdir()
    (smoke / "portable.metrics.json").write_text(json.dumps({"label": "portable", "ok": True, "report": {"shell": {}}}))
    signing = {"overall": "unsigned", "files": {setup: "NotSigned", "HorizonStudio.exe": "NotSigned",
                                                "core/horizon-studio-core.exe": "NotSigned"}}
    decision = {"policy": "unsigned-prerelease", "approved_by": "owner", "approved_at": "2026-10-31",
                "evidence": "test", "honoured": True}
    parity = {gate: True for gate in dr.PARITY_GATES} if ready else {"desktop-e2e": True}
    manifest = dr.build_manifest(VERSION, COMMIT, build.dist / setup, build.dist / portable,
                                 {gate: "success" for gate in dr.BUILD_GATES}, dr.smoke_results(smoke), signing, parity,
                                 channel="release", decision=decision if ready else None)
    (build.dist / release.DESKTOP_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    names = [release.exe_name(VERSION), "build-manifest.json", *release.desktop_names(VERSION)]
    (build.dist / "SHA256SUMS.txt").write_text(release.checksums(build.dist, names), encoding="ascii")
    return build


class NotesTests(unittest.TestCase):
    def test_accepts_matching_notes(self):
        self.assertEqual(release.check_notes(NOTES, VERSION), [])

    def test_rejects_another_versions_title_and_executable(self):
        # Exactly what happened to v0.6.0: the 0.5.0 text was published.
        stale = (ROOT / "docs" / "releases" / "v0.6.0.md").read_text(encoding="utf-8").replace("0.6.0", "0.5.0")
        problems = release.check_notes(stale, "0.6.0")
        self.assertTrue(any("Title" in p for p in problems))
        self.assertTrue(any("executable of version 0.5.0" in p for p in problems))
        mixed = NOTES + "\nAlso see HorizonStudio-0.1.0-Windows-x64.exe.\n"
        self.assertIn("Mentions the executable of version 0.1.0", release.check_notes(mixed, VERSION))

    def test_repository_notes_match_their_versions(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(release.check_notes((ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8"), version), [])
        for path in (ROOT / "docs" / "releases").glob("v*.md"):
            with self.subTest(path.name):
                self.assertEqual(release.check_notes(path.read_text(encoding="utf-8"), path.stem[1:]), [])


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.build = Build()
        self.exe = self.build.dist / release.exe_name(VERSION)

    def tearDown(self):
        self.build.close()

    def test_manifest_is_derived_from_the_real_build(self):
        manifest = json.loads((self.build.dist / "build-manifest.json").read_text())
        self.assertEqual(manifest["executable"]["sha256"], hashlib.sha256(self.exe.read_bytes()).hexdigest())
        self.assertEqual(manifest["git_commit"], COMMIT)
        self.assertEqual(manifest["signing"], "unsigned")
        self.assertRegex(manifest["built_at_utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")

    def test_refuses_mismatched_or_failed_inputs(self):
        cases = {
            "tag": dict(tag="v1.0.0"), "commit": dict(commit="main"),
            "failed gate": dict(gates={**GATES, "browser-e2e": "failure"}), "no gates": dict(gates={}),
            "smoke failed": dict(smoke={**SMOKE, "ok": False}), "smoke other version": dict(smoke={**SMOKE, "version": "1.0.0"}),
            "no smoke report": dict(smoke=None),
        }
        for label, override in cases.items():
            args = dict(version=VERSION, exe=self.exe, commit=COMMIT, tag=f"v{VERSION}", gates=GATES, smoke=SMOKE)
            args.update(override)
            with self.subTest(label), self.assertRaises(ReleaseError):
                release.build_manifest(**args)


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGitHub()
        self.build = Build()

    def tearDown(self):
        self.build.close()

    def publish(self, build=None, notes=NOTES, commit=COMMIT):
        return release.publish(self.gh, VERSION, commit, (build or self.build).dist, notes)

    def test_publishes_draft_first_then_verifies(self):
        result = self.publish()
        self.assertEqual(result["status"], "published")
        self.assertEqual(self.gh.tags[f"v{VERSION}"], COMMIT)
        kinds = [w[0] for w in self.gh.writes]
        self.assertEqual(kinds, ["create", "upload", "upload", "upload", "update"])
        self.assertFalse(self.gh.find_release(f"v{VERSION}")["draft"])

    def test_the_desktop_app_is_published_and_verified_with_the_release(self):
        desktop_build(self.build)
        result = release.publish(self.gh, VERSION, COMMIT, self.build.dist, NOTES, prerelease=False, desktop=True)
        self.assertEqual(result["status"], "published")
        self.assertTrue(result["prerelease"], "an unsigned desktop build is always a prerelease")
        self.assertEqual(result["desktop"]["signing"], "unsigned")
        self.assertEqual([a["name"] for a in result["desktop"]["assets"]], list(release.desktop_names(VERSION)))
        published = {a["name"] for a in self.gh.find_release(f"v{VERSION}")["assets"]}
        self.assertEqual(published, set(release.asset_names(VERSION, desktop=True)))
        # A rerun finds it complete and writes nothing.
        writes = len(self.gh.writes)
        self.assertEqual(release.publish(self.gh, VERSION, COMMIT, self.build.dist, NOTES, desktop=True)["status"],
                         "already verified")
        self.assertEqual(len(self.gh.writes), writes)

    def test_a_desktop_build_that_is_not_release_ready_is_never_uploaded(self):
        desktop_build(self.build, ready=False)
        with self.assertRaisesRegex(ReleaseError, "not release-ready"):
            release.publish(self.gh, VERSION, COMMIT, self.build.dist, NOTES, desktop=True)
        self.assertEqual(self.gh.writes, [])

    def test_a_tampered_desktop_asset_or_a_full_release_of_an_unsigned_build_fails_verification(self):
        desktop_build(self.build)
        release.publish(self.gh, VERSION, COMMIT, self.build.dist, NOTES, desktop=True)
        rel = self.gh.releases[0]
        rel["prerelease"] = False
        with self.assertRaisesRegex(ReleaseError, "full release"):
            release.verify(self.gh, VERSION, COMMIT)
        rel["prerelease"] = True
        setup = next(a for a in rel["assets"] if a["name"].endswith("-setup.exe"))
        setup["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ReleaseError, "setup.exe"):
            release.verify(self.gh, VERSION, COMMIT)

    def test_rerun_reports_already_verified_and_writes_nothing(self):
        self.publish()
        before = len(self.gh.writes)
        rebuilt = Build(b"MZ a rebuild with different bytes")
        try:
            self.assertEqual(self.publish(rebuilt)["status"], "already verified")
        finally:
            rebuilt.close()
        self.assertEqual(len(self.gh.writes), before, "a published binary must never be replaced")

    def test_tag_on_another_commit_stops_before_any_write(self):
        self.gh.tags[f"v{VERSION}"] = OTHER
        with self.assertRaisesRegex(ReleaseError, "tags are never moved"):
            self.publish()
        self.assertEqual(self.gh.writes, [])

    def test_wrong_notes_stop_before_any_write(self):
        with self.assertRaisesRegex(ReleaseError, "not for this version"):
            self.publish(notes=NOTES.replace(VERSION, "0.0.1"))
        self.assertEqual(self.gh.writes, [])

    def test_published_release_without_executable_is_an_integrity_violation(self):
        rel = self.gh.create_draft(f"v{VERSION}", COMMIT, "x", NOTES, True)
        self.gh._store(self.gh.releases[0], "SHA256SUMS.txt", b"x")
        self.gh.update(rel, draft=False)
        with self.assertRaisesRegex(ReleaseError, "incomplete or inconsistent"):
            self.publish()
        with self.assertRaisesRegex(ReleaseError, "missing asset"):
            release.verify(self.gh, VERSION, COMMIT)

    def test_interrupted_draft_is_completed_with_the_same_bytes(self):
        rel = self.gh.create_draft(f"v{VERSION}", COMMIT, "x", NOTES, True)
        exe = self.build.dist / release.exe_name(VERSION)
        self.gh.upload(rel, exe)
        result = self.publish()
        self.assertEqual(result["status"], "published")
        uploads = [w[1] for w in self.gh.writes if w[0] == "upload"]
        self.assertEqual(uploads.count(exe.name), 1)

    def test_corrupted_upload_keeps_the_release_a_draft(self):
        self.gh.corrupt_uploads = True
        with self.assertRaisesRegex(ReleaseError, "stays a draft"):
            self.publish()
        self.assertTrue(self.gh.find_release(f"v{VERSION}")["draft"])
        self.assertNotIn(f"v{VERSION}", self.gh.tags)

    def test_draft_holding_a_different_binary_is_not_overwritten(self):
        rel = self.gh.create_draft(f"v{VERSION}", COMMIT, "x", NOTES, True)
        other = Build(b"MZ another build")
        try:
            self.gh.upload(rel, other.dist / release.exe_name(VERSION))
        finally:
            other.close()
        with self.assertRaisesRegex(ReleaseError, "different"):
            self.publish()

    def test_verify_detects_checksum_mismatch_and_missing_release(self):
        with self.assertRaisesRegex(ReleaseError, "No GitHub release"):
            release.verify(self.gh, VERSION, COMMIT)
        self.publish()
        sums = next(a for a in self.gh.releases[0]["assets"] if a["name"] == "SHA256SUMS.txt")
        self.gh.blobs[sums["url"]] = b"0" * 64 + b"  " + release.exe_name(VERSION).encode()
        with self.assertRaisesRegex(ReleaseError, "SHA256SUMS.txt does not match"):
            release.verify(self.gh, VERSION, COMMIT)

    def test_repair_notes_changes_only_the_description(self):
        self.publish()
        before = json.dumps(self.gh.releases[0]["assets"])
        fixed = NOTES + "\nCorrected.\n"
        release.repair_notes(self.gh, VERSION, fixed)
        self.assertEqual(self.gh.releases[0]["body"], fixed)
        self.assertEqual(json.dumps(self.gh.releases[0]["assets"]), before)
        self.assertEqual(self.gh.writes[-1], ("update", ("body",)))
        with self.assertRaisesRegex(ReleaseError, "not for this version"):
            release.repair_notes(self.gh, VERSION, NOTES.replace(VERSION, "0.0.1"))


class BundleAndWorkflowTests(unittest.TestCase):
    def test_every_editor_script_is_bundled_and_served(self):
        import studio
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        loaded = set(re.findall(r'<script src="/([\w.]+\.js)"', html))
        self.assertEqual(loaded, set(studio.WEB_SCRIPTS))
        for name in studio.BUNDLED_FILES:
            self.assertTrue((ROOT / name).is_file(), name)
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_windows
        command = " ".join(build_windows.command(ROOT, VERSION, ";"))
        for name in studio.BUNDLED_FILES:
            self.assertIn(str(ROOT / name), command)

    def test_release_workflow_requires_every_gate_on_the_same_commit(self):
        text = (ROOT / ".github" / "workflows" / "windows-release.yml").read_text(encoding="utf-8")
        jobs = text.split("\njobs:\n", 1)[1]
        def block(name):
            match = re.search(rf"\n  {name}:\n(.*?)(?=\n  [\w-]+:\n|\Z)", "\n" + jobs, re.S)
            self.assertIsNotNone(match, name)
            return match.group(1)
        self.assertIn("uses: ./.github/workflows/tests.yml", block("tests"))
        self.assertIn("uses: ./.github/workflows/official-content-check.yml", block("official"))
        self.assertRegex(block("build"), r"needs: \[guard, tests, official\]")
        self.assertRegex(block("publish"), r"needs: \[guard, build, desktop\]")
        self.assertIn("uses: ./.github/workflows/desktop.yml", block("desktop"))
        self.assertIn("release: true", block("desktop"))
        self.assertIn("--desktop", block("publish"))
        self.assertNotIn("contents: write", block("desktop"))
        self.assertIn("workflow_call:", (ROOT / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8"))
        self.assertIn("contents: write", block("publish"))
        self.assertNotIn("contents: write", block("build"))
        self.assertIn("refs/heads/master", block("guard"))
        self.assertNotIn("pull_request", text.split("\njobs:\n", 1)[0])
        for workflow in ("tests.yml", "official-content-check.yml"):
            self.assertIn("workflow_call:", (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
