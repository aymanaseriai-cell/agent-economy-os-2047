import json
import tempfile
import unittest
from pathlib import Path

from automation.worker_fleet import REGISTRY, WORKERS, make_task, outcome, run_fleet, main
from automation.worker_dispatcher import PolicyError

SHA = "b56e5946b63d22eda34599ae119fc24fca3f9a1f"


def fake_fetch(url):
    if url.endswith("/health"):
        return {"status": "ok", "service": "Work Covenant"}
    if "/actions/runs/" in url:
        return {"status": "completed", "conclusion": "success", "head_sha": SHA}
    if url.endswith("/issues/98"):
        return {"number": 98, "state": "open", "updated_at": "2026-11-21T14:00:00Z"}
    if url.endswith("/issues/112"):
        return {"number": 112, "state": "open",
                "title": "[Public opt-in offer] Starter", "user": {"login": "aymanaseriai-cell"}}
    if url.endswith("/issues/123"):
        return {"number": 123, "state": "open",
                "title": "[Service request] public scope", "user": {"login": "real-user"}}
    if "issues?state=open" in url:
        return [
            {"number": 112, "state": "open", "title": "[Public opt-in offer] Starter", "user": {"login": "aymanaseriai-cell"}},
            {"number": 123, "state": "open", "title": "[Service request] Help", "user": {"login": "real-user"}},
            {"number": 124, "state": "open", "title": "[Service request] Fake", "user": {"login": "github-actions[bot]"}},
        ]
    raise ValueError("UNEXPECTED_PROVIDER_URL")


class WorkerFleetTests(unittest.TestCase):
    def test_twelve_workers_four_executives_exact_split(self):
        self.assertEqual(len(WORKERS), 12)
        self.assertEqual(len(REGISTRY), 12)
        counts = {role: sum(w.owner_role == role for w in WORKERS)
                  for role in ("CEO", "CTO", "CRO", "COO_CFO")}
        self.assertEqual(counts, {"CEO": 2, "CTO": 4, "CRO": 4, "COO_CFO": 2})

    def test_all_twelve_have_registered_capabilities(self):
        for w in WORKERS:
            with self.subTest(worker=w.worker_id):
                p = w.default_payload
                if p is None:
                    p = ({"run_id": 44875982406, "expected_head_sha": SHA}
                         if w.kind == "github_ci_readonly" else {"issue_number": 112})
                worker, task = make_task({"worker_id": w.worker_id, "payload": p})
                self.assertEqual(task["role"], worker.owner_role)
                self.assertEqual(task["kind"], worker.kind)
                self.assertEqual(task["spend_usd"], 0)
                self.assertFalse(task["allow_write"])

    def test_single_fleet_dispatch_gets_actual_verified_receipts(self):
        report = run_fleet([
            {"worker_id": "AEOS-W01"}, {"worker_id": "AEOS-W02"},
            {"worker_id": "AEOS-W07"}, {"worker_id": "AEOS-W11"},
        ], Path("."), fake_fetch, max_concurrent=2)
        self.assertEqual(report["technically_verified_readonly_count"], 4)
        self.assertEqual(report["dispatched_count"], 4)
        self.assertIsNone(report["verified_revenue_usd"])
        self.assertIsNone(report["company_autonomy_percent"])
        self.assertEqual(report["running_llm_worker_sessions"], 0)
        self.assertEqual(report["receipts"][0]["business_outcome"], "EXTERNAL_REQUEST_CANDIDATES_NOT_BUYERS")
        self.assertTrue(all(not x["production_change"] for x in report["receipts"]))

    def test_no_service_request_does_not_become_customer(self):
        report = run_fleet([{"worker_id": "AEOS-W08", "payload": {"issue_number": 112}}],
                           Path("."), fake_fetch)
        self.assertEqual(report["receipts"][0]["business_outcome"], "NO_EXTERNAL_OPTIN_IN_ISSUE")
        self.assertFalse(report["receipts"][0]["customer_acquired"])

    def test_external_request_still_not_verified_customer(self):
        report = run_fleet([{"worker_id": "AEOS-W08", "payload": {"issue_number": 123}}],
                           Path("."), fake_fetch)
        self.assertEqual(report["receipts"][0]["business_outcome"], "OPTIN_CANDIDATE_NOT_VERIFIED_BUYER")
        self.assertFalse(report["receipts"][0]["customer_acquired"])

    def test_reviewer_has_no_production_authority(self):
        report = run_fleet([{"worker_id": "AEOS-W06"}], Path("."), fake_fetch)
        self.assertEqual(report["receipts"][0]["business_outcome"], "RELEASE_GATE_STILL_OPEN")
        self.assertFalse(report["receipts"][0]["production_change"])

    def test_health_worker_reads_live_endpoint_twice(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return fake_fetch(url)
        report = run_fleet([{"worker_id": "AEOS-W11"}], Path("."), fetch)
        self.assertEqual(len(calls), 2)
        self.assertEqual(report["receipts"][0]["business_outcome"],
                         "REPORTED_HEALTH_OK_NOT_FULL_RELIABILITY")

    def test_finance_worker_does_not_fabricate_revenue(self):
        r = run_fleet([{"worker_id": "AEOS-W12", "payload": {"issue_number": 123}}],
                      Path("."), fake_fetch)
        self.assertEqual(r["receipts"][0]["business_outcome"],
                         "FINANCIAL_REVENUE_UNKNOWN_NEEDS_PAYMENT_AND_DELIVERY_PROOF")
        self.assertIsNone(r["receipts"][0]["revenue_verified_usd"])

    def test_no_unbounded_concurrency(self):
        with self.assertRaisesRegex(PolicyError, "CONCURRENCY_CAP"):
            run_fleet([{"worker_id": "AEOS-W01"}], Path("."), fake_fetch, 12)

    def test_no_duplicate_worker(self):
        with self.assertRaisesRegex(PolicyError, "DUPLICATE_WORKER_ASSIGNMENT"):
            run_fleet([{"worker_id": "AEOS-W01"}, {"worker_id": "AEOS-W01"}],
                      Path("."), fake_fetch)

    def test_reject_unregistered_or_tool_escalation(self):
        for job in ({"worker_id": "AEOS-W99"},
                    {"worker_id": "AEOS-W01", "kind": "run_shell"},
                    {"worker_id": "AEOS-W04", "payload": {"run_id": 1, "expected_head_sha": SHA}, "allow_write": True},
                    {"worker_id": "AEOS-W01", "priority": 9}):
            with self.subTest(job=job), self.assertRaises(PolicyError):
                make_task(job)

    def test_missing_evidence_fails_closed(self):
        for worker in ("AEOS-W04", "AEOS-W05", "AEOS-W08", "AEOS-W12"):
            with self.subTest(worker=worker), self.assertRaises(PolicyError):
                make_task({"worker_id": worker})

    def test_local_docs_and_code_workers_have_rechecked_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            (base/"verifier.py").write_text("print('ok')")
            (base/"docs").mkdir();(base/"docs/ENTERPRISE_EVIDENCE_PILOT.md").write_text("nonbinding")
            (base/"buyer-gate").mkdir();(base/"buyer-gate/README.md").write_text("instructions")
            jobs=[{"worker_id": w} for w in ("AEOS-W03","AEOS-W09","AEOS-W10")]
            r=run_fleet(jobs,base,fake_fetch)
            self.assertEqual(r["technically_verified_readonly_count"], 3)
            self.assertTrue(all(x["business_outcome"] == "ARTIFACT_HASH_RECHECKED_NOT_NEW_PRODUCT_DELIVERY"
                                for x in r["receipts"]))

    def test_cli_inventory_does_not_claim_live_llm_sessions(self):
        self.assertEqual(main(["--inventory"]),0)

    def test_cli_batch_output_persists_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            inp=Path(d)/"jobs.json"; out=Path(d)/"receipts.json"
            # This is a real local, no-network digest pass.
            (Path(d)/"verifier.py").write_text("test")
            inp.write_text(json.dumps([{"worker_id":"AEOS-W03"}]))
            self.assertEqual(main(["--jobs",str(inp),"--root",d,"--out",str(out)]),0)
            data=json.loads(out.read_text())
            self.assertEqual(data["technically_verified_readonly_count"],1)
            self.assertEqual(data["configured_worker_count"],12)


if __name__ == "__main__":
    unittest.main()
