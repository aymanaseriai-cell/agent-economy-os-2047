"""Offline checks for the public 750 USDC quote preflight (NO payment)."""
import base64
import json
import unittest
from io import BytesIO
from urllib.error import HTTPError

from automation.assessment_750_quote_guard import (
    BASE, SAMPLE, PREFLIGHT, REPORT, USDC, PAYEE,
    check_challenge, request, run, parse_payment_header,
)


class Response:
    def __init__(self, data):
        self.status = 200
        self.headers = {"Content-Type": "application/json"}
        self.data = json.dumps(data).encode()
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return None
    def read(self, limit):
        return self.data[:limit]


def good_quote():
    return {"x402Version": 2, "resource": {"url": REPORT},
            "accepts": [{"scheme": "exact", "network": "eip155:8453",
                         "asset": USDC, "amount": "750000000", "payTo": PAYEE}]}


def valid_preflight():
    return {"ok": True, "preflight": True, "paid": False,
            "amount_charged": 0, "price_usdc": "750.00",
            "report_delivered": False, "input_sha256": "a" * 64}


def sample():
    return {"synthetic": True, "paid": False,
            "input": {"schema": "agent-economy.reuse-guard.offline-evaluation.v1",
                      "consent": {"data_rights": True, "no_personal_data": True,
                                  "accepted_automated_scope": True}}}


class Opener:
    def __init__(self, quote=None, preflight=None, example=None, code=402):
        self.calls = []
        self.quote = good_quote() if quote is None else quote
        self.preflight = valid_preflight() if preflight is None else preflight
        self.example = sample() if example is None else example
        self.code = code
    def open(self, req, timeout):
        self.calls.append((req.full_url, req.get_method(), dict(req.headers), timeout))
        if req.full_url == SAMPLE:
            return Response(self.example)
        if req.full_url == PREFLIGHT:
            return Response(self.preflight)
        if req.full_url == REPORT:
            encoded = base64.b64encode(json.dumps(self.quote).encode()).decode()
            raise HTTPError(REPORT, self.code, "payment required",
                            {"PAYMENT-REQUIRED": encoded}, BytesIO(b""))
        raise AssertionError("unexpected network request")


class QuoteGuardTests(unittest.TestCase):
    def test_success_requires_exact_402_and_never_signs(self):
        opener = Opener()
        result = run(opener=opener)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["unsigned_paid_resource_requests"], 1)
        self.assertEqual(result["signed_payment_requests"], 0)
        self.assertEqual(result["payments_executed"], 0)
        self.assertIs(result["customer_or_revenue_verified"], False)
        self.assertEqual([x[0:2] for x in opener.calls],
                         [(SAMPLE, "GET"), (PREFLIGHT, "POST"), (REPORT, "POST")])
        for url, method, headers, timeout in opener.calls:
            self.assertEqual(timeout, 8)
            self.assertFalse(any("payment" in k.lower() or "authorization" in k.lower()
                                 for k in headers))

    def test_wrong_payee_amount_and_network_fail_closed(self):
        for key, bad_value in (("payTo", "0x" + "1"*40),
                               ("amount", "750000001"),
                               ("network", "eip155:1"),
                               ("asset", "0x" + "2"*40)):
            with self.subTest(key=key):
                challenge = good_quote()
                challenge["accepts"][0][key] = bad_value
                self.assertFalse(run(opener=Opener(quote=challenge))["ok"])
                with self.assertRaises(ValueError):
                    check_challenge(challenge)

    def test_invalid_preflight_stops_before_quote(self):
        bad = valid_preflight()
        bad["paid"] = True
        opener = Opener(preflight=bad)
        result = run(opener=opener)
        self.assertFalse(result["ok"])
        self.assertEqual(result["unsigned_paid_resource_requests"], 0)
        self.assertEqual(len(opener.calls), 2)

    def test_non_402_response_never_passes(self):
        result = run(opener=Opener(code=200))
        self.assertFalse(result["ok"])

    def test_invalid_synthetic_fixture_stops_before_post(self):
        bad = sample()
        bad["synthetic"] = False
        opener = Opener(example=bad)
        self.assertFalse(run(opener=opener)["ok"])
        self.assertEqual(len(opener.calls), 1)

    def test_request_allowlist(self):
        with self.assertRaises(ValueError):
            request("POST", "https://attacker.example/", b"{}")
        with self.assertRaises(ValueError):
            request("GET", REPORT)
        with self.assertRaises(ValueError):
            request("GET", SAMPLE, b"{}")

    def test_duplicate_and_overflow_json_challenges_fail(self):
        for raw in (b'{"x402Version":2,"x402Version":1}',
                    b'{"x402Version":2,"meta":1e10000}',
                    b'{"x402Version":2,"meta":NaN}'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_payment_header(base64.b64encode(raw).decode())

if __name__ == "__main__":
    unittest.main()
