"""Offline, synthetic claim-boundary acceptance cases for peer review."""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from automation.evidence_claim_boundaries import assess

PINNED = "c73494e447a11103522565d5aa90a2d6ae9eeeb42cde93628f4771ee71bf932e"
TUESDAY = b"Review is Tuesday"
THURSDAY = b"Review is Thursday"
FRIDAY = b"Review is Friday"


class ClaimBoundaryTests(unittest.TestCase):
    def evaluate(self, **overrides):
        kw = dict(saved=TUESDAY, current=THURSDAY, tampered=FRIDAY,
                  reference_sha256=PINNED, paths=["positive.json", "./positive.json"])
        kw.update(overrides)
        return assess(**kw)

    def test_saved_integrity_uses_separately_supplied_digest(self):
        r = self.evaluate()
        self.assertEqual(r["claims"]["saved_integrity"]["verdict"], "PASS")
        self.assertEqual(r["claims"]["saved_integrity"]["reference_trust"], "CALLER_SUPPLIED_UNVERIFIED")

    def test_changed_current_snapshot_not_misrepresented_as_freshness(self):
        r = self.evaluate()
        self.assertTrue(r["claims"]["current_freshness"]["different_snapshot_observed"])
        self.assertEqual(r["claims"]["current_freshness"]["verdict"], "NOT_PROVEN")

    def test_independent_anchor_is_not_credited_from_digest_alone(self):
        self.assertEqual(self.evaluate()["claims"]["independent_anchor"]["verdict"], "NOT_PROVEN")

    def test_tamper_a_changed_bytes_with_same_reference_fails(self):
        r = self.evaluate(saved=FRIDAY)
        self.assertEqual(r["claims"]["saved_integrity"]["verdict"], "FAIL")
        self.assertEqual(r["adversarial"]["tamper_a"]["verdict"], "DETECTED")

    def test_tamper_b_producer_changed_both_bytes_and_digest_not_anchored(self):
        r = self.evaluate(saved=FRIDAY)
        self.assertTrue(r["adversarial"]["tamper_b"]["producer_self_consistency"])
        self.assertEqual(r["adversarial"]["tamper_b"]["verdict"], "NOT_PROVEN")
        self.assertTrue(r["adversarial"]["tamper_b"]["fails_caller_reference"])

    def test_aliases_fail_closed_but_distinct_paths_pass(self):
        self.assertEqual(self.evaluate()["claims"]["alias_uniqueness"]["verdict"], "FAIL_CLOSED")
        self.assertEqual(self.evaluate(paths=["positive.json", "current.json"])["claims"]["alias_uniqueness"]["verdict"], "PASS")

    def test_unsafe_path_refused(self):
        with self.assertRaises(ValueError):
            self.evaluate(paths=["../secret", "positive.json"])

    def test_invalid_reference_refused(self):
        with self.assertRaises(ValueError):
            self.evaluate(reference_sha256="deadbeef")

    def test_json_cli_no_network_or_keys(self):
        repo = Path(__file__).resolve().parents[1]
        cli = [sys.executable, "-m", "automation.evidence_claim_boundaries",
               "--fixture-dir", str(repo / "fixtures" / "open-evidence-lab-352" / "two-version"),
               "--reference-sha256", PINNED]
        p = subprocess.run(cli, check=True, text=True, capture_output=True, cwd=repo, timeout=12)
        result = json.loads(p.stdout)
        self.assertEqual(result["schema"], "agent-economy.claim-boundaries.v1")
        self.assertEqual(result["claims"]["saved_integrity"]["verdict"], "PASS")
        self.assertEqual(result["claims"]["current_freshness"]["verdict"], "NOT_PROVEN")
        self.assertEqual(result["claims"]["alias_uniqueness"]["verdict"], "FAIL_CLOSED")


if __name__ == "__main__":
    unittest.main()

