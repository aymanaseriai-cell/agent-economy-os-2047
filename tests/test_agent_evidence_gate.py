"""Replay, scope, tampering, alias and trust-boundary checks."""
import hashlib
import json
import tempfile
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


if __name__ == "__main__":
    unittest.main()
