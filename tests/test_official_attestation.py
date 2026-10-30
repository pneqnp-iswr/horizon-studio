"""Contract tests for pinned official checker evidence (not in-game)."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.record_official_evidence import attest, main

SHA = "d2186eb9aa022a64a8b26e6989a04e44fba99ee7"


class AttestationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.checker = root / "cargo-horizon-mod"
        self.checker.write_bytes(b"fixture: not a real validator")
        self.evidence = root / "checker.json"
        self.report = {
            "stage": "official",
            "ok": True,
            "sha256": "a" * 64,
            "size": 123,
            "exit_code": 0,
            "declared_validator_revision": SHA,
            "command": [str(self.checker), "check", "/tmp/fixture.hmod", "--json"],
            "report": {"ok": True, "report": {
                "sha256": "a" * 64, "size": 123, "kind": "mod", "api": "0.2"}},
        }
        self.write_result()

    def tearDown(self):
        self.tmp.cleanup()

    def write_result(self):
        self.evidence.write_text(json.dumps(self.report), encoding="utf-8")

    def test_attests_only_successful_correlated_result(self):
        proof = attest(self.checker, SHA, self.evidence)
        self.assertTrue(proof["passed"])
        self.assertFalse(proof["in_game_tested"])
        self.assertEqual(proof["checker_binary_sha256"],
                         hashlib.sha256(self.checker.read_bytes()).hexdigest())
        self.assertEqual(proof["checked_mod_sha256"], "a" * 64)

    def test_rejects_failed_official_check(self):
        self.report["ok"] = False
        self.write_result()
        with self.assertRaisesRegex(ValueError, "passing"):
            attest(self.checker, SHA, self.evidence)

    def test_rejects_wrong_binary(self):
        self.report["command"][0] = "/tmp/untrusted-binary"
        self.write_result()
        with self.assertRaisesRegex(ValueError, "executable"):
            attest(self.checker, SHA, self.evidence)

    def test_rejects_revision_mismatch(self):
        self.report["declared_validator_revision"] = "f" * 40
        self.write_result()
        with self.assertRaisesRegex(ValueError, "different"):
            attest(self.checker, SHA, self.evidence)

    def test_rejects_different_hash_or_package_size(self):
        self.report["report"]["report"]["size"] = 124
        self.write_result()
        with self.assertRaisesRegex(ValueError, "size"):
            attest(self.checker, SHA, self.evidence)
        self.report["report"]["report"]["size"] = 123
        self.report["report"]["report"]["sha256"] = "b" * 64
        self.write_result()
        with self.assertRaisesRegex(ValueError, "digest"):
            attest(self.checker, SHA, self.evidence)

    def test_creates_verifiable_machine_readable_file(self):
        output = Path(self.tmp.name) / "out" / "attestation.json"
        self.assertEqual(main(["--checker", str(self.checker), "--checker-revision", SHA,
                               "--official-result", str(self.evidence),
                               "--output", str(output)]), 0)
        self.assertEqual(json.loads(output.read_text())["schema"],
                         "horizon-studio.official-compat/1")

    def test_rejects_unpinned_revision(self):
        with self.assertRaisesRegex(ValueError, "pinned"):
            attest(self.checker, "main", self.evidence)


if __name__ == "__main__":
    unittest.main()
