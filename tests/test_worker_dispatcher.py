import json
import tempfile
import unittest
from pathlib import Path
from automation.worker_dispatcher import dispatch, evaluate, PolicyError, main, safe_local_file

SHA = "b56e5946b63d22eda34599ae119fc24fca3f9a1f"


def task(kind="github_ci_readonly", role="CTO", payload=None, **kw):
    if payload is None:
        payload = {"run_id": 44875982406, "expected_head_sha": SHA}
    return {"id": "CTO-CHECK-1", "role": role, "kind": kind, "payload": payload, **kw}


class WorkerDispatchTests(unittest.TestCase):
    def test_valid_ci_receipt_is_rechecked(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return {"status": "completed", "conclusion": "success", "head_sha": SHA, "html_url": "https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/runs/44875982406"}
        result = dispatch(task(), Path("."), fetch)
        self.assertEqual(result["status"], "VERIFIED_READONLY")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(len(calls), 2)
        self.assertFalse(result["outbound_contact"])

    def test_changed_provider_receipt_blocked_after_bounded_retry(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return {"status": "completed", "conclusion": "success", "head_sha": SHA if len(calls) % 2 else "a"*40, "html_url": "https://github.com/..."}
        result = dispatch(task(), Path("."), fetch)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(len(calls), 4)

    def test_failed_ci_not_success(self):
        def fetch(url):
            return {"status": "completed", "conclusion": "failure", "head_sha": SHA, "html_url": "https://github.com/..."}
        result = dispatch(task(), Path("."), fetch)
        self.assertEqual(result["verification"], "CI_NOT_PASSING_ON_EXPECTED_SHA")
        self.assertEqual(result["status"], "BLOCKED")

    def test_external_issue_is_not_buyer_or_contact_permission(self):
        doc = {"number": 77, "state": "open", "user": {"login": "real-elsewhere"}, "title": "[Service request] Audit"}
        inbound = task("github_inbound_readonly", "CRO", {"issue_number": 77})
        result = dispatch(inbound, Path("."), lambda url: doc)
        self.assertEqual(result["status"], "VERIFIED_READONLY")
        self.assertTrue(result["evidence"]["outside_opt_in_candidate"])
        self.assertFalse(result["evidence"]["verified_buyer"])
        self.assertFalse(result["evidence"]["contact_authorized"])

    def test_owner_issue_does_not_fake_external_adoption(self):
        doc = {"number": 112, "state": "open", "user": {"login": "aymanaseriai-cell"}, "title": "[Service request] Audit"}
        result = dispatch(task("github_inbound_readonly", "CRO", {"issue_number": 112}), Path("."), lambda url: doc)
        self.assertFalse(result["evidence"]["outside_opt_in_candidate"])

    def test_permitted_local_digest_recomputed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "safe.json"; p.write_text('{"value":1}')
            t = task("local_file_digest", "CTO", {"path": "safe.json"})
            result = dispatch(t, Path(d))
            self.assertEqual(result["status"], "VERIFIED_READONLY")
            self.assertEqual(result["evidence"]["bytes"], 11)

    def test_denies_traversal_symlink_and_absolute_path(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "link").symlink_to("/etc/passwd")
            for path in ("../foo", "/etc/passwd", "link"):
                with self.subTest(path=path), self.assertRaises(PolicyError):
                    safe_local_file(base, path)

    def test_denies_unapproved_roles_writes_and_spend(self):
        for t in (task(role="CRO"), task(spend_usd=1), task(allow_write=True), task(max_attempts=0)):
            with self.subTest(t=t), self.assertRaises(PolicyError):
                evaluate(t)

    def test_no_unbounded_attempts(self):
        with self.assertRaises(PolicyError):
            evaluate(task(max_attempts=99))

    def test_real_work_covenant_health_shape_is_verified(self):
        calls = []
        response = {"ok": True, "service": "agent-work-covenant-2047",
                    "stateless": True, "no_paid_actions": True}
        def fetch(url):
            calls.append(url)
            return response
        checked = dispatch(task("http_health_readonly", "COO_CFO", {}), Path("."), fetch)
        self.assertEqual(checked["status"], "VERIFIED_READONLY")
        self.assertEqual(checked["evidence"]["reported_health"], "healthy")
        self.assertFalse(checked["evidence"]["production_release_authorized"])
        self.assertEqual(len(calls), 2)

    def test_unknown_or_contradictory_health_fails_closed(self):
        health_task = task("http_health_readonly", "COO_CFO", {})
        samples = (
            {"unexpected": "JSON not evidence of service health"},
            {"ok": True, "service": "agent-work-covenant-2047"},
            {"ok": False, "status": "ok", "service": "agent-work-covenant-2047",
             "stateless": True, "no_paid_actions": True},
            {"status": "degraded", "service": "other"},
        )
        for document in samples:
            with self.subTest(document=document):
                result = dispatch(health_task, Path("."), lambda url: document)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertEqual(result["attempts"], 2)
                self.assertEqual(result["verification"], "HEALTH_NOT_CONFIRMED")

    def test_cli_writes_true_receipt_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); (base / "f").write_text("hello")
            t = task("local_file_digest", "CTO", {"path": "f"})
            file = base / "tasks.json"; file.write_text(json.dumps([t]))
            out = base / "receipt.json"
            self.assertEqual(main(["--tasks", str(file), "--root", d, "--out", str(out)]), 0)
            report = json.loads(out.read_text())
            self.assertEqual(report["receipts"][0]["status"], "VERIFIED_READONLY")
            file.write_text(json.dumps([t,t]))
            self.assertEqual(main(["--tasks", str(file), "--root", d, "--out", str(out)]), 2)


if __name__ == "__main__":
    unittest.main()
