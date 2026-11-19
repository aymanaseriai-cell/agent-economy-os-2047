"""Adversarial regression tests for buyer-held exact evidence replay gate."""
import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from evidence_gate import issue_challenge, redeem_challenge
from verifier import validate


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "private" / "ledger.sqlite3"
        (self.root / "result.txt").write_bytes(b"completed-work-v1")
        self.manifest = self.root / "manifest.json"
        self.write_manifest()

    def write_manifest(self):
        digest = hashlib.sha256((self.root / "result.txt").read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps({"artifacts": [{"path": "result.txt", "sha256": digest}]}))

    def issue(self, **kwargs):
        return issue_challenge(self.ledger, self.manifest, now=1000, **kwargs)["challenge"]

    def redeem(self, challenge, **kwargs):
        return redeem_challenge(self.ledger, self.manifest, self.root, challenge, now=1001, **kwargs)

    def test_original_verifier_does_not_prevent_duplicate_acceptance(self):
        self.assertTrue(validate(self.manifest, self.root)["passed"])
        self.assertTrue(validate(self.manifest, self.root)["passed"])

    def test_one_time_acceptance_and_no_raw_challenge_in_database(self):
        token = self.issue()
        first = self.redeem(token)
        self.assertEqual(first["status"], "accepted_once")
        self.assertFalse(first["buyer_acceptance_verified"])
        self.assertFalse(first["payment_verified"])
        self.assertRegex(first["receipt_id"], r"^[0-9a-f]{64}$")
        self.assertEqual(self.redeem(token)["reason"], "challenge_already_redeemed")
        with sqlite3.connect(self.ledger) as db:
            raw = str(db.execute("SELECT * FROM challenges").fetchall())
        self.assertNotIn(token, raw)

    def test_exact_proof_cannot_be_claimed_using_new_token(self):
        old = self.issue()
        self.assertTrue(self.redeem(old)["accepted"])
        new = self.issue()
        self.assertEqual(self.redeem(new)["reason"], "exact_evidence_reused")

    def test_same_evidence_with_reformatted_manifest_is_still_reused(self):
        first = self.issue()
        self.assertTrue(self.redeem(first)["accepted"])
        payload = json.loads(self.manifest.read_text())
        self.manifest.write_text(json.dumps(payload, indent=4))
        second = self.issue()
        self.assertEqual(self.redeem(second)["reason"], "exact_evidence_reused")

    def test_new_artifact_content_can_be_accepted(self):
        first = self.issue()
        self.assertTrue(self.redeem(first)["accepted"])
        (self.root / "result.txt").write_text("completed-work-v2")
        self.write_manifest()
        second = self.issue()
        self.assertTrue(self.redeem(second)["accepted"])

    def test_expiry_unknown_or_invalid_token(self):
        token = self.issue(ttl_seconds=1)
        self.assertEqual(self.redeem(token)["reason"], "challenge_expired")
        self.assertEqual(self.redeem("x" * 44)["reason"], "unknown_challenge")
        self.assertEqual(self.redeem("bad")["reason"], "invalid_challenge")

    def test_modified_manifest_is_rejected_and_does_not_consume_token(self):
        token = self.issue()
        self.manifest.write_text(self.manifest.read_text() + "\n")
        self.assertEqual(self.redeem(token)["reason"], "manifest_mismatch")
        self.manifest.write_text(self.manifest.read_text().rstrip())
        self.assertEqual(self.redeem(token)["status"], "accepted_once")

    def test_tampered_artifact_never_consumes_token(self):
        token = self.issue()
        (self.root / "result.txt").write_text("tampered")
        self.assertEqual(self.redeem(token)["reason"], "artifact_validation_failed")
        (self.root / "result.txt").write_bytes(b"completed-work-v1")
        self.assertTrue(self.redeem(token)["accepted"])

    def test_duplicate_artifact_path_is_rejected(self):
        payload = json.loads(self.manifest.read_text())
        payload["artifacts"].append({"path": "./result.txt", "sha256": payload["artifacts"][0]["sha256"]})
        self.manifest.write_text(json.dumps(payload))
        self.assertEqual(self.redeem(self.issue())["reason"], "duplicate_artifact_path")

    def test_absolute_path_and_traversal_rejected(self):
        payload = json.loads(self.manifest.read_text())
        payload["artifacts"][0]["path"] = str(self.root / "result.txt")
        self.manifest.write_text(json.dumps(payload))
        self.assertEqual(self.redeem(self.issue())["reason"], "invalid_artifact_path")
        payload["artifacts"][0]["path"] = "../escape.txt"
        self.manifest.write_text(json.dumps(payload))
        self.assertEqual(self.redeem(self.issue())["reason"], "path_escapes_root")

    def test_invalid_manifest_and_ttl_fail_closed(self):
        with self.assertRaises(ValueError):
            issue_challenge(self.ledger, self.manifest, ttl_seconds=0)
        self.manifest.write_text("{")
        with self.assertRaises(ValueError):
            issue_challenge(self.ledger, self.manifest)

    def test_simultaneous_redemptions_only_one_accepted(self):
        token = self.issue()
        barrier = threading.Barrier(2)
        results = []
        def worker():
            barrier.wait(timeout=3)
            results.append(self.redeem(token))
        x, y = threading.Thread(target=worker), threading.Thread(target=worker)
        x.start(); y.start(); x.join(timeout=6); y.join(timeout=6)
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(bool(r["accepted"]) for r in results), 1)
        self.assertEqual(sum(r["reason"] == "challenge_already_redeemed" for r in results if not r["accepted"]), 1)


if __name__ == "__main__":
    unittest.main()
