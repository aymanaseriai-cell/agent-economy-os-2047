"""Offline synthetic fixtures for the fixed public Work Covenant end-to-end smoke."""
import json
import unittest

from automation.work_covenant_live_smoke import (
    COMPILE, DEMO, EVALUATE, build_request, run
)


class FakeResponse:
    def __init__(self, value):
        self.status = 200
        self.headers = {"Content-Type": "application/json; charset=utf-8"}
        self.content = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, count):
        return self.content[:count]


CONTRACT = {
    "schema": "agent-economy.work-covenant.v1",
    "scope": "caller_supplied_work_requirements_only",
    "task": {"title": "Generate reproducible JSON report", "id": "demo_public_qa"},
    "criteria": [
        {"id": "report_exists", "type": "artifact_exists", "artifact": "report.json"},
        {"id": "status_ok", "type": "json_pointer_equals", "artifact": "report.json",
         "pointer": "/ok", "expected": True},
        {"id": "report_test", "type": "test_summary", "suite": "unit",
         "min_passed": 3, "max_failed": 0},
    ],
}
ID = "a" * 64


def review(status, passed, fail_status):
    result = [{"id": "report_exists", "pass": True},
              {"id": "status_ok", "pass": not fail_status},
              {"id": "report_test", "pass": True}]
    return {"ok": True, "status": status, "contract_id": ID,
            "passed": passed, "total": 3, "proof_id": ("c" if fail_status else "b") * 64,
            "results": result, "buyer_acceptance_verified": False,
            "payment_verified": False, "onchain_settlement_verified": False,
            "evidence_covers_supplied_bytes_only": True}


class FakeOpener:
    def __init__(self, accept_tamper=False, paid_claim=False):
        self.calls = []
        self.accept_tamper = accept_tamper
        self.paid_claim = paid_claim

    def open(self, req, timeout):
        self.calls.append((req.full_url, req.method, dict(req.headers), timeout))
        if req.full_url == DEMO:
            return FakeResponse({"ok": True, "contract": CONTRACT, "contract_id": ID,
                                 "sample_submission": {
                                     "artifacts": [{"name": "report.json", "content": '{"ok":true}'}],
                                     "reported_tests": [{"suite": "unit", "passed": 3, "failed": 0}]}})
        if req.full_url == COMPILE:
            return FakeResponse({"ok": True, "status": "compiled",
                                 "contract": CONTRACT, "contract_id": ID})
        if req.full_url == EVALUATE:
            body = json.loads(req.data.decode("utf-8"))
            items = body["submission"]["artifacts"]
            tampered = items[0]["content"] == '{"ok":false}'
            status = "local_checks_passed" if self.accept_tamper or not tampered else "local_checks_failed"
            item = review(status, 3 if self.accept_tamper or not tampered else 2, tampered and not self.accept_tamper)
            if self.paid_claim:
                item["payment_verified"] = True
            return FakeResponse(item)
        raise AssertionError("Unexpected endpoint")


class WorkCovenantLiveSmokeTests(unittest.TestCase):
    def test_four_fixed_no_payment_requests_and_rejection(self):
        opened = FakeOpener()
        result = run(opened)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["completed_requests"], 4)
        self.assertTrue(result["untampered_fixture_accepted"])
        self.assertTrue(result["tampered_fixture_rejected"])
        self.assertEqual(result["payment_requests"], 0)
        self.assertFalse(result["customer_or_revenue_verified"])
        self.assertEqual([x[0] for x in opened.calls], [DEMO, COMPILE, EVALUATE, EVALUATE])
        self.assertEqual([x[1] for x in opened.calls], ["GET", "POST", "POST", "POST"])
        for url, method, headers, timeout in opened.calls:
            self.assertEqual(timeout, 8)
            self.assertFalse(any("payment" in k.lower() or "authorization" in k.lower()
                                 for k in headers))

    def test_bad_server_claims_fail_closed(self):
        self.assertFalse(run(FakeOpener(accept_tamper=True))["ok"])
        self.assertFalse(run(FakeOpener(paid_claim=True))["ok"])

    def test_non_allowlisted_url_and_body_on_get_blocked(self):
        with self.assertRaises(ValueError):
            build_request("POST", "https://attacker.example/", {})
        with self.assertRaises(ValueError):
            build_request("GET", DEMO, {})
        with self.assertRaises(ValueError):
            build_request("GET", EVALUATE)

    def test_invalid_post_payload_blocked(self):
        with self.assertRaises(ValueError):
            build_request("POST", EVALUATE, {"payload": "x" * 25000})


if __name__ == "__main__":
    unittest.main()
