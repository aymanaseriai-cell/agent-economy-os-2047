import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_trust_preflight import BASE_USDC, read_challenge, reserve_quote, InvalidInput

URL = "https://api.example.test/v1/verify"
PAYEE = "0x" + "ab" * 20
POLICY = {"resource_url": URL, "payee": PAYEE,
          "max_quote_micro": 10000, "daily_budget_micro": 50000}


def quote(amount="10000"):
    return {"x402Version": 2, "resource": {"url": URL}, "accepts": [{
      "scheme": "exact", "network": "eip155:8453", "asset": BASE_USDC,
      "payTo": PAYEE, "amount": amount, "maxTimeoutSeconds": 300
    }]}


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "budget.sqlite3")

    def reserve(self, ident="safe-request-00001", challenge=None, policy=None):
        return reserve_quote(challenge=quote() if challenge is None else challenge,
            raw_policy=POLICY if policy is None else policy, operation_id=ident, db_path=self.db)

    def test_valid_quote_only_reserves_never_authorizes_or_pays(self):
        d = self.reserve()
        self.assertEqual(d["state"], "reserved_preflight_only")
        self.assertTrue(d["reservation_created"])
        for key in ("eligible_for_new_execution", "payment_authorized", "payment_executed",
                    "settlement_verified", "identity_verified"):
            self.assertFalse(d[key])

    def test_same_operation_is_blocked_even_with_same_quote(self):
        self.reserve()
        d = self.reserve()
        self.assertEqual(d["state"], "duplicate_operation")
        self.assertFalse(d["reservation_created"])

    def test_same_operation_with_modified_quote_is_rejected(self):
        self.reserve()
        d = self.reserve(challenge=quote("9000"))
        self.assertEqual(d["state"], "operation_conflict")

    def test_aggregate_daily_budget(self):
        for i in range(5):
            self.assertTrue(self.reserve(f"request-unique-{i:05d}")["reservation_created"])
        last = self.reserve("request-unique-99999")
        self.assertEqual(last["state"], "budget_exceeded")
        self.assertEqual(last["total_reserved_today_micro"], 50000)

    def test_concurrent_reservations_cannot_exceed_budget(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            output = list(pool.map(lambda i: self.reserve(f"parallel-req-{i:07d}"), range(24)))
        self.assertEqual(sum(r["reservation_created"] for r in output), 5)
        self.assertEqual(sum(r["state"] == "budget_exceeded" for r in output), 19)

    def test_wrong_payee_chain_asset_resource_and_scheme(self):
        cases = [("payTo", "0x" + "cd" * 20), ("network", "eip155:1"),
                 ("asset", "0x" + "cd" * 20), ("scheme", "upto")]
        for field, value in cases:
            x = quote(); x["accepts"][0][field] = value
            self.assertEqual(self.reserve(challenge=x)["state"], "quote_rejected", field)
        x = quote(); x["resource"]["url"] = "https://other.example.test/pay"
        self.assertEqual(self.reserve(challenge=x)["state"], "quote_rejected")

    def test_amount_and_types_fail_closed(self):
        for bad in ("0", "10001", "01", "1e3", "1.0", "-1", 10000, True, "١٠٠٠"):
            self.assertEqual(self.reserve(challenge=quote(bad))["state"], "quote_rejected", repr(bad))
        x = quote(); x["x402Version"] = True
        self.assertEqual(self.reserve(challenge=x)["state"], "quote_rejected")

    def test_multi_offer_and_timeout(self):
        x = quote(); x["accepts"].append(x["accepts"][0]); self.assertEqual(self.reserve(challenge=x)["state"], "quote_rejected")
        x = quote(); x["accepts"][0]["maxTimeoutSeconds"] = 1000
        self.assertEqual(self.reserve(challenge=x)["state"], "quote_rejected")

    def test_invalid_identifier_or_policy_denied(self):
        self.assertEqual(self.reserve(ident="bad")["state"], "invalid_operation_id")
        self.assertEqual(self.reserve(policy={**POLICY, "daily_budget_micro": 0})["state"], "policy_rejected")
        self.assertEqual(self.reserve(policy={**POLICY, "resource_url": "http://127.0.0.1/"})["state"], "policy_rejected")

    def test_policy_lock_prevents_silent_policy_change(self):
        self.reserve()
        changed = {**POLICY, "daily_budget_micro": 100000}
        self.assertEqual(self.reserve(ident="new-operation-0001", policy=changed)["state"], "policy_lock_mismatch")

    def test_corrupt_ledger_fails_closed(self):
        Path(self.db).write_text("NOT SQLITE")
        self.assertEqual(self.reserve()["state"], "ledger_unavailable")

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(InvalidInput):
            read_challenge(b'{"x402Version":2,"x402Version":1}')

    def test_raw_and_base64_captures(self):
        raw = json.dumps(quote()).encode("utf-8")
        self.assertEqual(read_challenge(raw), quote())
        self.assertEqual(read_challenge(base64.b64encode(raw)), quote())
        self.assertEqual(read_challenge(base64.urlsafe_b64encode(raw).rstrip(b"=")), quote())

    def test_capture_limit_and_malformed(self):
        for raw in (b"", b"xx", b"X" * 65537, b"{broken}", b"[]", b'{"x":NaN}'):
            with self.assertRaises(InvalidInput):
                read_challenge(raw)


if __name__ == "__main__":
    unittest.main()