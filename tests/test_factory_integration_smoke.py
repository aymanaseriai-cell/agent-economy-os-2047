import unittest
from pathlib import Path

from automation.factory_integration_smoke import run_factory_smoke, synthetic_reviewonly_orders
from automation.worker_dispatcher import PolicyError

SHA = "b56e5946b63d22eda34599ae119fc24fca3f9a1f"


def jobs():
    return [
        {"worker_id": "AEOS-W01", "payload": {}},
        {"worker_id": "AEOS-W04", "payload": {"run_id": 44875982406, "expected_head_sha": SHA}},
        {"worker_id": "AEOS-W07", "payload": {}},
        {"worker_id": "AEOS-W11", "payload": {}},
    ]


def fetch(url):
    if "/issues?state=open" in url:
        return []
    if "/actions/runs/" in url:
        return {"status": "completed", "conclusion": "success", "head_sha": SHA,
                "path": ".github/workflows/ci.yml",
                "repository": {"full_name": "aymanaseriai-cell/agent-economy-os-2047"}}
    if url.endswith("/health"):
        return {"ok": True, "service": "agent-work-covenant-2047",
                "stateless": True, "no_paid_actions": True}
    raise ValueError("UNEXPECTED_PROVIDER_URL")


class FactoryIntegrationTests(unittest.TestCase):
    def test_four_managers_choose_exactly_one_synthetic_job_each(self):
        orders = synthetic_reviewonly_orders()
        self.assertEqual(len(orders), 4)
        self.assertEqual({o["owner_role"] for o in orders}, {"CEO", "CTO", "CRO", "COO_CFO"})

    def test_reviewonly_factory_executes_realistic_provider_scopes(self):
        report = run_factory_smoke(jobs(), Path("."), fetch=fetch)
        self.assertEqual(report["integration_status"], "PASSED")
        self.assertEqual(report["verified_readonly_count"], 4)
        self.assertEqual(report["dispatched_count"], 4)
        self.assertEqual(len(report["worker_receipts"]), 4)
        self.assertFalse(report["production_change"])
        self.assertFalse(report["autonomous_code_repair_verified"])
        self.assertFalse(report["external_customer_served"])
        self.assertIsNone(report["verified_revenue_usd"])
        self.assertEqual(report["independent_llm_sessions"], 0)
        self.assertIn("SYNTHETIC", report["source_orders"])

    def test_broken_real_ci_fails_closed_instead_of_claiming_success(self):
        def failed_ci(url):
            if "/actions/runs/" in url:
                return {"status": "completed", "conclusion": "failure", "head_sha": SHA,
                        "path": ".github/workflows/ci.yml",
                        "repository": {"full_name": "aymanaseriai-cell/agent-economy-os-2047"}}
            return fetch(url)
        report = run_factory_smoke(jobs(), Path("."), fetch=failed_ci)
        self.assertEqual(report["integration_status"], "DEGRADED")
        self.assertEqual(report["verified_readonly_count"], 3)
        self.assertEqual(report["worker_receipts"][1]["technical_status"], "BLOCKED")

    def test_missing_selected_worker_blocks_execution(self):
        with self.assertRaisesRegex(PolicyError, "MISSING_EXACT_SELECTED_JOB"):
            run_factory_smoke(jobs()[:-1], Path("."), fetch=fetch)


if __name__ == "__main__":
    unittest.main()
