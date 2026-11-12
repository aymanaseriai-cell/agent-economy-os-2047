"""Deterministic, offline tests: no wallet, network, API keys or spending."""
import base64
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "examples" / "x402_quote_guard.py"
SPEC = importlib.util.spec_from_file_location("x402_quote_guard", SOURCE)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

URL = "https://merchant.example/api/receipt"
PAYEE = "0x935ad91b70c6d0769871416c5904d06fbf9ef586"


def offer():
    return {"x402Version": 2, "resource": {"url": URL}, "accepts": [{
        "scheme": "exact", "network": "eip155:8453", "asset": MODULE.BASE_USDC,
        "payTo": PAYEE, "amount": "10000", "maxTimeoutSeconds": 300,
    }]}


class TestQuoteGuard(unittest.TestCase):
    def verdict(self, obj):
        return MODULE.inspect(obj, expected_url=URL, expected_payee=PAYEE, max_atomic=10000)

    def test_valid_exact_quote_is_not_payment_authorization(self):
        v = self.verdict(offer())
        self.assertTrue(v["eligible"])
        self.assertFalse(v["payment_authorized"])
        self.assertFalse(v["payment_executed"])

    def test_encoded_header(self):
        raw = json.dumps(offer()).encode()
        self.assertEqual(MODULE.read_challenge(base64.b64encode(raw)), offer())
        self.assertEqual(MODULE.read_challenge(raw), offer())

    def test_wrong_chain(self):
        q = offer(); q["accepts"][0]["network"] = "eip155:1"
        self.assertIn("network_mismatch", self.verdict(q)["errors"])

    def test_wrong_recipient(self):
        q = offer(); q["accepts"][0]["payTo"] = "0x" + "1" * 40
        self.assertIn("payee_mismatch", self.verdict(q)["errors"])

    def test_wrong_token(self):
        q = offer(); q["accepts"][0]["asset"] = "0x" + "1" * 40
        self.assertIn("asset_mismatch", self.verdict(q)["errors"])

    def test_wrong_url(self):
        q = offer(); q["resource"]["url"] += "?another=1"
        self.assertIn("resource_url_mismatch", self.verdict(q)["errors"])

    def test_overpriced(self):
        q = offer(); q["accepts"][0]["amount"] = "10001"
        self.assertIn("amount_outside_pinned_limit", self.verdict(q)["errors"])

    def test_integer_and_float_amounts_rejected(self):
        for value in (10000, 10000.0, "10.000", "00010000", "1e4", "-1", "1\u0660"):
            q = offer(); q["accepts"][0]["amount"] = value
            self.assertIn("invalid_atomic_amount", self.verdict(q)["errors"])

    def test_unsupported_version(self):
        q = offer(); q["x402Version"] = True
        self.assertIn("unsupported_x402_version", self.verdict(q)["errors"])

    def test_multiple_offers_fail_closed(self):
        q = offer(); q["accepts"].append(dict(q["accepts"][0]))
        self.assertIn("requires_exactly_one_payment_offer", self.verdict(q)["errors"])

    def test_missing_offer(self):
        q = offer(); q["accepts"] = []
        self.assertFalse(self.verdict(q)["eligible"])

    def test_scheme_or_timeout_mismatch(self):
        q = offer(); q["accepts"][0]["scheme"] = "other"
        q["accepts"][0]["maxTimeoutSeconds"] = 1000
        self.assertIn("scheme_mismatch", self.verdict(q)["errors"])
        self.assertIn("timeout_outside_pinned_range", self.verdict(q)["errors"])

    def test_duplicate_json_keys_rejected(self):
        raw = b'{"x402Version":2,"x402Version":1}'
        with self.assertRaises(MODULE.InvalidChallenge):
            MODULE.read_challenge(raw)

    def test_broken_header_rejected(self):
        for raw in (b'!!', b'', b'abcdef', b'{not json}', b'x' * (64 * 1024 + 1)):
            with self.assertRaises(MODULE.InvalidChallenge):
                MODULE.read_challenge(raw)

    def test_invalid_pins(self):
        with self.assertRaises(ValueError):
            MODULE.inspect(offer(), expected_url='http://insecure', expected_payee=PAYEE, max_atomic=10000)
        with self.assertRaises(ValueError):
            MODULE.inspect(offer(), expected_url=URL, expected_payee=PAYEE, max_atomic=-1)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "challenge.json"
            p.write_text(json.dumps(offer()))
            args = [str(p), "--expected-url", URL, "--expected-payee", PAYEE, "--max-atomic", "10000"]
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(MODULE.main(args), 0)
            q = offer(); q["accepts"][0]["amount"] = "9999999"
            p.write_text(json.dumps(q))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(MODULE.main(args), 2)


if __name__ == "__main__":
    unittest.main()
