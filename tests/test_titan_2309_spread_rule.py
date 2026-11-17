"""Only new entry condition for TITAN Omega 23:09: spread <=8 basis points.

Tests use simulated public OKX ticker/instrument responses. No trading/orders.
"""
import time
import unittest
from decimal import Decimal
from trading.okx_live_executor import market_preflight, CandidateRejected, MAX_SPREAD_BP

class PublicMarket:
    def __init__(self, bid, ask):
        self.bid,self.ask=bid,ask

    def request(self, method, path, params=None, auth=False):
        if method!="GET":
            raise AssertionError("Only public GET allowed")
        if path=="/api/v5/market/ticker":
            return [{
                "instId":"TEST-USDT-SWAP","last":"100",
                "bidPx":self.bid,"askPx":self.ask,
                "volCcy24h":"200000", "ts":str(int(time.time()*1000))
            }]
        if path=="/api/v5/public/instruments":
            return [{
                "instId":"TEST-USDT-SWAP","state":"live","instCategory":"1",
                "ctType":"linear","settleCcy":"USDT","ctValCcy":"TEST",
                "ruleType":"normal","lever":"20"
            }]
        raise AssertionError("Unexpected request: "+path)

class TightSpreadTest(unittest.TestCase):
    def test_only_new_condition_is_eight_basis_points(self):
        self.assertEqual(MAX_SPREAD_BP,Decimal("8"))

    def test_buy_and_sell_with_tight_spread_are_eligible(self):
        for side in ("LONG","SHORT"):
            for bid,ask in (("99.97","100.03"),("99.96","100.04")):
                with self.subTest(side=side,bid=bid,ask=ask):
                    t,inst=market_preflight(PublicMarket(bid,ask),
                        {"symbol":"TEST-USDT-SWAP","signal":side,"quote_price":"100"})
                    self.assertEqual(inst["state"],"live")
                    self.assertEqual(t["instId"],"TEST-USDT-SWAP")

    def test_wider_spread_rejected_symmetric(self):
        for side in ("LONG","SHORT"):
            with self.subTest(side=side):
                with self.assertRaisesRegex(CandidateRejected,"Spread too wide"):
                    market_preflight(PublicMarket("99.95","100.05"),
                        {"symbol":"TEST-USDT-SWAP","signal":side,"quote_price":"100"})

if __name__=="__main__":
    unittest.main()
