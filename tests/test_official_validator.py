"""HS-001: official checker adapter contracts, failure modes, and CLI wiring."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from horizon_compat.official_validator import check_hmod
from horizon_cli import main
from studio import hmod_zip

PACKAGE = hmod_zip({"id":"official_probe","name":"Probe","version":"0.1.0","author":"Test",
                    "blocks":[],"items":[{"id":"probe","name":"Probe","template":"minecraft:diamond"}],"recipes":[],"structures":[]})


class OfficialValidatorTests(unittest.TestCase):
    def success(self, command, **kwargs):
        archive = Path(command[-2])
        self.assertTrue(archive.is_file())
        self.assertTrue(archive.read_bytes().startswith(b"PK"))
        self.assertEqual(command[0:3], ["cargo", "horizon-mod", "check"])
        self.assertEqual(command[-1], "--json")
        content = archive.read_bytes()
        report = {"kind":"mod","api":"0.2","sha256":hashlib.sha256(content).hexdigest(),
                  "size":len(content),"id":"official_probe"}
        return subprocess.CompletedProcess(command, 0, json.dumps({"ok":True,"report":report}), "")

    @patch("horizon_compat.official_validator.subprocess.run")
    def test_accepts_official_report_with_matching_hash(self, run):
        run.side_effect=self.success
        result=check_hmod(PACKAGE)
        self.assertTrue(result.ok)
        self.assertEqual(result.stage,"official")
        self.assertEqual(result.sha256,hashlib.sha256(PACKAGE).hexdigest())
        self.assertIsNone(result.error)
        run.assert_called_once()
        self.assertIs(run.call_args.kwargs["stdin"],subprocess.DEVNULL)

    @patch("horizon_compat.official_validator.subprocess.run")
    def test_rejects_hash_mismatch(self, run):
        run.return_value=subprocess.CompletedProcess(["cargo"],0,json.dumps({
            "ok":True,"report":{"kind":"mod","api":"0.2","sha256":"0"*64,"size":len(PACKAGE)}}),"")
        result=check_hmod(PACKAGE)
        self.assertFalse(result.ok)
        self.assertIn("inconsistent",result.error)

    @patch("horizon_compat.official_validator.subprocess.run")
    def test_rejects_lying_exit_status_or_wrong_kind(self, run):
        run.return_value=subprocess.CompletedProcess(["cargo"],1,json.dumps({
            "ok":True,"report":{"kind":"mod","api":"0.2","sha256":hashlib.sha256(PACKAGE).hexdigest(),"size":len(PACKAGE)}}),"")
        self.assertFalse(check_hmod(PACKAGE).ok)
        run.return_value=subprocess.CompletedProcess(["cargo"],0,json.dumps({
            "ok":True,"report":{"kind":"native","api":"0.2","sha256":hashlib.sha256(PACKAGE).hexdigest(),"size":len(PACKAGE)}}),"")
        self.assertFalse(check_hmod(PACKAGE).ok)

    @patch("horizon_compat.official_validator.subprocess.run")
    def test_reports_rejection_and_bad_output(self, run):
        run.return_value=subprocess.CompletedProcess(["cargo"],1,json.dumps({"ok":False,"error":"Bad manifest"}),"detail")
        result=check_hmod(PACKAGE)
        self.assertFalse(result.ok)
        self.assertIn("Bad manifest",result.error)
        run.return_value=subprocess.CompletedProcess(["cargo"],0,"garbage","")
        self.assertIn("expected JSON",check_hmod(PACKAGE).error)

    @patch("horizon_compat.official_validator.subprocess.run", side_effect=FileNotFoundError())
    def test_missing_binary_not_marked_pass(self, _run):
        result=check_hmod(PACKAGE)
        self.assertFalse(result.ok)
        self.assertIn("not installed",result.error)

    @patch("horizon_compat.official_validator.subprocess.run", side_effect=subprocess.TimeoutExpired(["cargo"], 2))
    def test_timeout_not_marked_pass(self, _run):
        result=check_hmod(PACKAGE,timeout=2)
        self.assertFalse(result.ok)
        self.assertIn("timed out",result.error)

    def test_requires_full_revision_if_declared(self):
        with self.assertRaisesRegex(ValueError,"revision"):
            check_hmod(PACKAGE,declared_validator_revision="latest")

    @patch("horizon_cli.check_hmod")
    def test_cli_verify_writes_evidence(self, checker):
        from horizon_compat.official_validator import OfficialCheckResult
        checker.return_value=OfficialCheckResult("official",False,"a"*64,len(PACKAGE),["cargo"],None,None,"missing")
        project=Path(__file__).resolve().parents[1] / "examples" / "ruby_demo.hstudio.json"
        with tempfile.TemporaryDirectory() as d:
            evidence=Path(d)/"sub"/"proof.json"
            self.assertEqual(main(["verify",str(project),"--evidence",str(evidence),"--json"]),1)
            payload=json.loads(evidence.read_text(encoding="utf-8"))
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["stage"],"official")
            self.assertIn("sha256",payload)


if __name__ == '__main__':
    unittest.main()
