import base64
import json
import unittest
from automation.agent402_seller_watch import (
    PAYEE, CHAIN, USDC, QUERY, ROUTES, check_index, check_quote, find_rank
)

def header(payee=PAYEE, amount="5000", network=CHAIN, asset=USDC):
    quote = {"x402Version": 2, "accepts": [{
        "scheme": "exact", "network": network, "asset": asset,
        "payTo": payee, "amount": amount
    }]}
    return {"payment-required": base64.urlsafe_b64encode(json.dumps(quote).encode()).decode().rstrip("=")}

def sample_tool():
    return {"method": "GET", "route": "/api/v1/receipt", "price": 0.005,
            "executeViaCallableNow": True, "executeViaLane": "unproven",
            "routerDispatchByChain": {"base": {"unprovenTier": True, "unprovenMaxUsd": 0.05}}}

def sample_index(origin):
    return {"origin": origin, "health": 1, "routable": True,
            "routerDispatchEligible": False, "routerDispatchReason": "settlement_required",
            "tools": [sample_tool()]}

class SellerWatchTests(unittest.TestCase):
    def test_challenge_true_and_no_payment(self):
        v = check_quote(402, header(), 5000)
        self.assertTrue(v["ok"])
        self.assertFalse(v["payment_submitted"])

    def test_bad_payee_rejected(self):
        self.assertFalse(check_quote(402, header(payee="0x" + "0" * 40), 5000)["ok"])

    def test_wrong_price_rejected(self):
        self.assertFalse(check_quote(402, header(amount="9000"), 5000)["ok"])

    def test_wrong_chain_and_token_rejected(self):
        self.assertFalse(check_quote(402, header(network="eip155:1"), 5000)["ok"])
        self.assertFalse(check_quote(402, header(asset="0x" + "0" * 40), 5000)["ok"])

    def test_missing_quote_rejected(self):
        self.assertFalse(check_quote(200, {}, 5000)["ok"])
        self.assertFalse(check_quote(402, {"payment-required": "garbage"}, 5000)["ok"])

    def test_tool_unproven_is_callable_even_when_origin_flag_false(self):
        origin = "https://example.supabase.co/receipt"
        v = check_index(sample_index(origin), origin, 5000)
        self.assertTrue(v["ok"])
        self.assertFalse(v["origin_level_dispatch_eligible"])
        self.assertEqual(v["tool_level_execute_lane"], "unproven")

    def test_tool_not_callable_rejected(self):
        origin = "https://example.supabase.co/receipt"
        index = sample_index(origin)
        index["tools"][0]["executeViaCallableNow"] = False
        self.assertFalse(check_index(index, origin, 5000)["ok"])

    def test_wrong_origin_rejected(self):
        self.assertFalse(check_index(sample_index("https://bad.example"), "https://trusted.example", 5000)["ok"])

    def test_bountytruth_marketplace_route_uses_expected_path(self):
        route = "/api/v1/audit"
        origin = "https://example.supabase.co/functions/v1/agent-bounty-truth-gate"
        index = sample_index(origin)
        index["tools"][0]["route"] = route
        self.assertTrue(check_index(index, origin, 5000, route)["ok"])
        self.assertFalse(check_index(index, origin, 5000, "/api/v1/receipt")["ok"])

    def test_bountytruth_route_is_in_monitoring_roster(self):
        self.assertIn(("agent-bounty-truth-gate", 5000, "/api/v1/audit"), ROUTES)

    def test_bountytruth_discovery_rank(self):
        x = {"results": [{"seller": "https://example.test/bounty", "route": "/api/v1/audit"}]}
        self.assertEqual(find_rank(x, "https://example.test/bounty", "/api/v1/audit"), 1)

    def test_ranking_not_interpreted_as_payment(self):
        a = "https://example.supabase.co/receipt"
        self.assertEqual(find_rank({"results": [{"seller": a, "route": "/api/v1/receipt"}]}, a), 1)
        self.assertIsNone(find_rank({"results": []}, a))

if __name__ == "__main__":
    unittest.main()
