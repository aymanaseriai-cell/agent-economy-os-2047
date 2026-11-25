"""Standalone ZIP delivery and honest buyer-policy trust boundary regression tests."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "distribution" / "agensi"))
from build_skill import FILES, build

EXPECTED = {
    "SKILL.md",
    "scripts/check.py",
    "examples/policy.json",
    "examples/deliverables/report.json",
    "LICENSE",
}


class MarketplaceBuyerAcceptanceTests(unittest.TestCase):
    def test_archive_is_reproducible_and_contains_only_allowlisted_files(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp, "one.zip"), Path(temp, "two.zip")
            self.assertEqual(build(a), build(b))
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with zipfile.ZipFile(a) as z:
                self.assertEqual(set(z.namelist()), EXPECTED)
                self.assertEqual(len(z.namelist()), len(set(z.namelist())))
                for name, source in FILES.items():
                    self.assertEqual(z.read(name), source.read_bytes())
                    self.assertFalse(name.startswith("/") or ".." in Path(name).parts)

    def test_offline_synthetic_pass_and_modified_output_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            archive = root / "portable.zip"
            build(archive)
            extract = root / "skill"
            with zipfile.ZipFile(archive) as z:
                z.extractall(extract)
            policy = extract / "examples" / "policy.json"
            pin = hashlib.sha256(policy.read_bytes()).hexdigest()
            result_file = root / "result.json"
            command = [
                sys.executable, str(extract / "scripts" / "check.py"),
                str(policy), "--policy-sha256", pin,
                "--root", str(extract / "examples"), "--json-out", str(result_file),
            ]
            passed = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(passed.returncode, 0, passed.stderr + passed.stdout[:800])
            result = json.loads(result_file.read_text(encoding="utf-8"))
            self.assertTrue(result["local_checks_passed"])
            for field in ("buyer_identity_verified", "buyer_authority_verified",
                          "agent_execution_verified", "independent_provenance_verified",
                          "source_freshness_verified", "payment_verified"):
                self.assertFalse(result[field])
            artifact = extract / "examples" / "deliverables" / "report.json"
            artifact.write_text('{"status":"manipulated","reviewer_notes":"none"}',
                                encoding="utf-8")
            failed = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(failed.returncode, 1)
            self.assertFalse(json.loads(result_file.read_text(encoding="utf-8"))["local_checks_passed"])

    def test_bad_pin_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "portable.zip"
            build(dest)
            extracted = Path(d) / "skill"
            with zipfile.ZipFile(dest) as z:
                z.extractall(extracted)
            result = subprocess.run([
                sys.executable, str(extracted / "scripts" / "check.py"),
                str(extracted / "examples" / "policy.json"),
                "--policy-sha256", "0" * 64,
                "--root", str(extracted / "examples"),
            ], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            data = json.loads(result.stdout)
            self.assertFalse(data["local_checks_passed"])
            self.assertFalse(data["policy_pin_matched"])


if __name__ == "__main__":
    unittest.main()
