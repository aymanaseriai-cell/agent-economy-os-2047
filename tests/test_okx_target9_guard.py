import unittest
from trading.okx_target9_guard import check_target, usdt_equity
from trading.okx_live_executor import ExecutionBlocked


def pos(symbol="BTC-USDT-SWAP", margin="isolated", side="net"):
    return {"instId": symbol, "mgnMode": margin, "posSide": side, "pos": "2"}


class Fake:
    def __init__(self, eq="9.2", positions=None, normal=None, algos=None,
                 mode="net_mode", uncertain=False, stale=False):
        self.eq, self.positions = eq, list(positions or [])
        self.normal, self.algos = list(normal or []), list(algos or [])
        self.mode, self.uncertain, self.stale = mode, uncertain, stale
        self.posts = []

    def request(self, method, path, *, params=None, body=None, auth=True):
        if method == "GET":
            if path == "/api/v5/account/balance":
                return [{"details": [{"ccy": "USDT", "eq": self.eq}], "totalEq": "100000"}]
            if path == "/api/v5/account/config":
                return [{"posMode": self.mode}]
            if path == "/api/v5/account/positions":
                return list(self.positions)
            if path == "/api/v5/trade/orders-pending":
                return list(self.normal)
            if path == "/api/v5/trade/orders-algo-pending":
                return [x for x in self.algos if x.get("ordType") == params["ordType"]]
        self.posts.append((path, body))
        if self.uncertain:
            raise ExecutionBlocked("unknown outcome")
        if path == "/api/v5/trade/cancel-order":
            if not self.stale:
                self.normal = [x for x in self.normal if x["ordId"] != body["ordId"]]
            return [{"sCode": "0", "ordId": body["ordId"]}]
        if path == "/api/v5/trade/close-position":
            self.positions = [x for x in self.positions if any(
                x[k] != body[k] for k in ("instId", "mgnMode", "posSide"))]
            self.eq = "8.97"
            return [{"instId": body["instId"], "posSide": body["posSide"]}]
        if path == "/api/v5/trade/cancel-algos":
            ids = {(x["instId"], x["algoId"]) for x in body}
            self.algos = [x for x in self.algos if (x["instId"], x["algoId"]) not in ids]
            return [{"sCode": "0", "algoId": x["algoId"]} for x in body]
        raise AssertionError(path)


def run(fake, armed=True):
    return check_target(fake, close_armed=armed, pause=lambda seconds: None)


class TargetTests(unittest.TestCase):
    def test_usdt_equity_not_total_usd(self):
        f = Fake(eq="4.53")
        self.assertEqual(str(usdt_equity(f)), "4.53")
        self.assertEqual(run(f), "BELOW_TARGET")
        self.assertFalse(f.posts)

    def test_at_exact_nine_flat(self):
        f = Fake(eq="9")
        self.assertEqual(run(f), "TARGET9_FLAT")
        self.assertFalse(f.posts)

    def test_close_two_positions_and_verify(self):
        f = Fake(positions=[pos(), pos("DOGE-USDT-SWAP")])
        self.assertEqual(run(f), "TARGET9_FLAT")
        closes = [b for p, b in f.posts if p.endswith("close-position")]
        self.assertEqual(len(closes), 2)
        self.assertTrue(all(x["autoCxl"] for x in closes))
        self.assertEqual(f.eq, "8.97")

    def test_hedged_cross_isolated(self):
        f = Fake(positions=[pos(margin="cross", side="long"),
                            pos(margin="isolated", side="short")], mode="long_short_mode")
        self.assertEqual(run(f), "TARGET9_FLAT")
        self.assertFalse(f.positions)

    def test_cancel_pending_before_close(self):
        f = Fake(positions=[pos()], normal=[{"instId": "BTC-USDT-SWAP", "ordId": "123"}])
        self.assertEqual(run(f), "TARGET9_FLAT")
        self.assertEqual([x[0] for x in f.posts[:2]],
                         ["/api/v5/trade/cancel-order", "/api/v5/trade/close-position"])

    def test_cancel_orphan_algo(self):
        f = Fake(algos=[{"instId": "BTC-USDT-SWAP", "algoId": "51", "ordType": "oco"}])
        self.assertEqual(run(f), "TARGET9_FLAT")
        self.assertEqual(f.posts[0][0], "/api/v5/trade/cancel-algos")

    def test_not_armed_no_writes(self):
        f = Fake(positions=[pos()])
        with self.assertRaises(ExecutionBlocked):
            run(f, armed=False)
        self.assertFalse(f.posts)

    def test_order_cancel_uncertain_no_close(self):
        f = Fake(positions=[pos()], normal=[{"instId": "BTC-USDT-SWAP", "ordId": "5"}],
                 stale=True)
        with self.assertRaises(ExecutionBlocked):
            run(f)
        self.assertEqual(len(f.posts), 1)

    def test_unsupported_exposure_no_write(self):
        for p in (pos(symbol="BTC-USD-SWAP"), pos(margin="unknown"), pos(side="short")):
            with self.subTest(position=p):
                f = Fake(positions=[p])
                with self.assertRaises(ExecutionBlocked):
                    run(f)
                self.assertFalse(f.posts)

    def test_unsupported_pending_no_write(self):
        f = Fake(positions=[pos()], normal=[{"instId": "BTC-USD-SWAP", "ordId": "1"}])
        with self.assertRaises(ExecutionBlocked):
            run(f)
        self.assertFalse(f.posts)

    def test_unknown_outcome_not_retried(self):
        f = Fake(positions=[pos()], uncertain=True)
        with self.assertRaises(ExecutionBlocked):
            run(f)
        self.assertEqual(len(f.posts), 1)

    def test_invalid_equity(self):
        for equity in ("NaN", "Infinity", "-1", "bad"):
            with self.subTest(equity=equity), self.assertRaises(ExecutionBlocked):
                run(Fake(eq=equity))


if __name__ == "__main__":
    unittest.main()
