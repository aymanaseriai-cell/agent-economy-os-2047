#!/usr/bin/env python3
"""Unit checks for the synthetic four-verdict fixture."""
import copy
import json
import unittest
from pathlib import Path
from verify_handoff_claims_v1_1 import classify, safe_unique_posix_paths, sha256_text, validate_fixture
HERE = Path(__file__).resolve().parent
BASE = json.loads((HERE / "handoff_claims_v1_1.json").read_text(encoding="utf-8"))["cases"][0]

class HandoffBoundaryTests(unittest.TestCase):
    def test_fixture_cases(self):
        self.assertEqual(validate_fixture(HERE / "handoff_claims_v1_1.json"), 0)
    def test_canonical_hashes(self):
        self.assertEqual(sha256_text("Review is Tuesday"), "c73494e447a11103522565d5aa90a2d6ae9eeeb42cde93628f4771ee71bf932e")
        self.assertEqual(sha256_text("Review is Thursday"), "88d22d4086bd19032301d060b95e92132a29daabe054b3ce7f99c582740fceed")
        self.assertEqual(sha256_text("Review is Friday"), "10a23c87553d04091e5fbd0b2fdce9eef92db89445925ea4cc44feb3d8067691")
    def test_no_live_source_freshness_claim(self):
        c = copy.deepcopy(BASE); c["current_version"] = "extremely-new-label"; c["current_bytes"] = "Review is Friday"
        v, d = classify(c)
        self.assertEqual(v["current_freshness"], "UNVERIFIED_SOURCE_FRESHNESS")
        self.assertEqual(d["current_snapshot_integrity"], "FAIL")
    def test_self_digest_is_not_provenance(self):
        c = copy.deepcopy(BASE); c["saved_bytes"] = "Review is Friday"; c["saved_digest"] = sha256_text(c["saved_bytes"])
        v, _ = classify(c)
        self.assertEqual(v["saved_integrity"], "PASS")
        self.assertEqual(v["independent_anchor"], "NOT_PROVEN")
    def test_mismatching_reference_fails(self):
        c = copy.deepcopy(BASE); c["saved_bytes"] = "Review is Friday"; c["saved_digest"] = sha256_text(c["saved_bytes"]); c["anchor_digest"] = BASE["saved_digest"]
        v, _ = classify(c)
        self.assertEqual(v["independent_anchor"], "FAIL")
    def test_matching_reference_does_not_prove_external_custody(self):
        c = copy.deepcopy(BASE); c["anchor_digest"] = c["saved_digest"]
        self.assertEqual(classify(c)[0]["independent_anchor"], "NOT_PROVEN")
    def test_posix_alias_and_unsafe_paths(self):
        for bad in (["a", "./a"], ["a", "a"], ["../a"], ["/root/a"], ["a\\b"], ["."], ["a", "a/../a"]):
            with self.subTest(bad=bad):
                self.assertFalse(safe_unique_posix_paths(bad))
        self.assertTrue(safe_unique_posix_paths(["a", "b"]))
    def test_malformed_digest_fails_closed(self):
        c = copy.deepcopy(BASE); c["saved_digest"] = "xx"
        with self.assertRaises(ValueError):
            classify(c)
    def test_missing_schema_fails_closed(self):
        c = copy.deepcopy(BASE); del c["saved_bytes"]
        with self.assertRaises(ValueError):
            classify(c)

if __name__ == "__main__":
    unittest.main()
