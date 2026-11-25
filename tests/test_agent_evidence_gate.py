"""Replay, scope, tampering, alias and trust-boundary checks."""
import hashlib
import json
import tempfile
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import unittest
from pathlib import Path
from agent_evidence_gate import issue, verify, manifest_hash


class TestEvidenceGate(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name) / "root"
        self.root.mkdir()
        self.db = Path(self.t.name) / "gate.sqlite"
        self.file = self.root / "output.txt"
        self.file.write_text("correct")
        self.manifest = Path(self.t.name) / "manifest.json"
        self.entry = {"path": "output.txt", "sha256": hashlib.sha256(b"correct").hexdigest()}
        self.write([self.entry])

    def write(self, rows):
        self.manifest.write_text(json.dumps({"artifacts": rows}))

    def create(self, ttl=60):
        return issue(self.db, "task-A", "agent-B", manifest_hash(self.manifest),
                     ttl=ttl, now=100)["nonce"]

    def check(self, nonce, now=101, request="task-A", audience="agent-B"):
        return verify(self.db, nonce, request, audience,
                      self.manifest, self.root, now=now)

    def test_valid_receipt_with_explicit_limits(self):
        out = self.check(self.create())
        self.assertTrue(out["passed"])
        self.assertEqual(len(out["receipt_sha256"]), 64)
        self.assertEqual(out["artifacts_checked"], 1)
        self.assertFalse(out["payment_verified"])
        self.assertFalse(out["independent_identity_verified"])

    def test_replay(self):
        nonce = self.create()
        self.assertTrue(self.check(nonce)["passed"])
        self.assertEqual(self.check(nonce)["status"], "replay_blocked")

    def test_expiry(self):
        self.assertEqual(self.check(self.create(), now=160)["status"],
                         "challenge_expired")

    def test_request_binding(self):
        self.assertEqual(self.check(self.create(), request="task-Z")["status"],
                         "binding_mismatch")

    def test_audience_binding(self):
        self.assertEqual(self.check(self.create(), audience="agent-Z")["status"],
                         "binding_mismatch")

    def test_modified_artifact_and_retry(self):
        nonce = self.create()
        self.file.write_text("tampered")
        self.assertEqual(self.check(nonce)["status"], "artifact_integrity_failed")
        self.file.write_text("correct")
        self.assertTrue(self.check(nonce)["passed"])

    def test_manifest_changed(self):
        nonce = self.create()
        self.manifest.write_text(self.manifest.read_text() + "\n")
        self.assertEqual(self.check(nonce)["status"], "manifest_mismatch")

    def test_duplicate_artifact(self):
        self.write([self.entry, self.entry])
        self.assertEqual(self.check(self.create())["status"], "duplicate_artifact")

    def test_traversal_alias(self):
        self.write([dict(self.entry, path="a/../output.txt")])
        self.assertEqual(self.check(self.create())["status"], "unsafe_path")

    def test_symlink(self):
        (self.root / "link.txt").symlink_to("output.txt")
        self.write([dict(self.entry, path="link.txt")])
        self.assertEqual(self.check(self.create())["status"], "symlink_rejected")

    def test_unknown_nonce(self):
        self.assertEqual(self.check("0" * 48)["status"], "challenge_unknown")

    def test_invalid_issue_data(self):
        with self.assertRaises(ValueError):
            issue(self.db, "bad id", "agent", "0" * 64)
        with self.assertRaises(ValueError):
            issue(self.db, "good", "agent", "0" * 64, ttl=0)


    def test_reissued_nonce_same_scoped_evidence_rejected(self):
        first, second = self.create(), self.create()
        self.assertTrue(self.check(first)["passed"])
        self.assertEqual(self.check(second)["status"], "evidence_reused_or_replay")

    def test_same_bytes_different_scope_allowed(self):
        self.assertTrue(self.check(self.create())["passed"])
        n = issue(self.db, "task-Z", "agent-B", manifest_hash(self.manifest), now=100)["nonce"]
        self.assertTrue(self.check(n, request="task-Z")["passed"])

    def test_eight_concurrent_attempts_single_acceptance(self):
        n = self.create()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.check(n), range(8)))
        self.assertEqual(sum(x["passed"] for x in results), 1)

    def test_expiry_rechecked_at_atomic_claim(self):
        n = self.create()
        with patch("agent_evidence_gate.time.time", side_effect=[101, 160]):
            out = verify(self.db, n, "task-A", "agent-B", self.manifest, self.root)
        self.assertFalse(out["passed"])
        self.assertEqual(out["status"], "replay_or_expired")
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM evidence_claims").fetchone()[0], 0)

    def test_validation_uses_pinned_snapshot(self):
        from verifier import validate as actual
        n = self.create()
        pinned = self.manifest.read_bytes()
        def mutate_then_validate(path, root):
            self.manifest.write_text("{}")
            self.assertEqual(path.read_bytes(), pinned)
            return actual(path, root)
        with patch("agent_evidence_gate.validate", side_effect=mutate_then_validate):
            self.assertTrue(self.check(n)["passed"])

    def test_legacy_consumption_unknown_fails_closed(self):
        first, second = self.create(), self.create()
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE evidence_challenges SET used_at=101 WHERE nonce=?", (first,))
        self.assertEqual(self.check(second)["status"], "legacy_claim_history_unverified")

    def test_failed_consumption_rolls_back_claim(self):
        n = self.create()
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TRIGGER fail_update BEFORE UPDATE OF used_at ON evidence_challenges BEGIN SELECT RAISE(ABORT,'fixture'); END")
        self.assertFalse(self.check(n)["passed"])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM evidence_claims").fetchone()[0], 0)
            db.execute("DROP TRIGGER fail_update")
        self.assertTrue(self.check(n)["passed"])

    def test_unknown_nonce_does_not_create_database(self):
        self.assertEqual(self.check("0" * 48)["status"], "challenge_unknown")
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
