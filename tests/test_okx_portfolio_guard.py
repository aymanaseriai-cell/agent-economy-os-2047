import unittest
from decimal import Decimal
from trading.okx_portfolio_guard import snapshot, sizing_equity, check_new, UnsafePortfolio, RiskLimitExceeded, NEW_ENTRY_CAP_FRACTION

def pos(s="BTC-USDT-SWAP",qty="1"):
    return {"instId":s,"pos":qty,"mgnMode":"isolated","markPx":"100","notionalUsd":"2000"}
def algo(s="BTC-USDT-SWAP",sl="99"):
    return {"instId":s,"tpTriggerPx":"102","slTriggerPx":sl}
class Fake:
    def __init__(self, positions=None, algos=None, pending=None):
        self.positions=positions or []; self.algos=algos or []; self.pending=pending or []
    def request(self, method, path, params=None, body=None):
        assert method=="GET" and body is None
        if path.endswith("/config"):return [{"posMode":"net_mode"}]
        if path.endswith("/positions"):return self.positions
        if path.endswith("/orders-pending"):return self.pending
        if path.endswith("/orders-algo-pending"):
            return self.algos if params["ordType"]=="oco" else []
        if path.endswith("/balance"):
            return [{"totalEq":"1000","details":[{"ccy":"USDT","availEq":"800"}]}]
        raise AssertionError(path)
class MultiPositionGuardTests(unittest.TestCase):
    def test_empty_account(self):
        s=snapshot(Fake())
        self.assertEqual(s["symbols"],frozenset())
        self.assertEqual(sizing_equity(s),Decimal("800"))
    def test_one_covered_position(self):
        s=snapshot(Fake([pos()],[algo()]))
        self.assertEqual(s["planned"],Decimal("20"))
        check_new(s,Decimal("1000"),Decimal("0.01"))
    def test_two_covered_positions(self):
        s=snapshot(Fake([pos(),pos("ETH-USDT-SWAP","-1")],
                        [algo(),algo("ETH-USDT-SWAP","101")]))
        self.assertEqual(len(s["symbols"]),2)
    def test_unprotected_position_fails(self):
        with self.assertRaisesRegex(UnsafePortfolio,"TP/SL"):
            snapshot(Fake([pos()]))
    def test_orphan_fails(self):
        with self.assertRaisesRegex(UnsafePortfolio,"Orphan"):
            snapshot(Fake([],[algo()]))
    def test_foreign_cross_margin_fails(self):
        p=pos();p["mgnMode"]="cross"
        with self.assertRaisesRegex(UnsafePortfolio,"Non-isolated"):
            snapshot(Fake([p],[algo()]))
    def test_ten_individually_protected_positions_pass_and_eleventh_fails(self):
        names = ("BTC", "ETH", "SOL", "XRP", "DOGE", "ADA",
                 "LINK", "AVAX", "DOT", "LTC", "TRX")
        covered = []
        protective = []
        for name in names:
            p=pos(name+"-USDT-SWAP")
            p["notionalUsd"]="100"
            covered.append(p)
            protective.append(algo(name+"-USDT-SWAP"))
        state=snapshot(Fake(covered[:10],protective[:10]))
        self.assertEqual(len(state["symbols"]),10)
        self.assertEqual(state["planned"],Decimal("10"))
        self.assertEqual(state["notional"],Decimal("1000"))
        with self.assertRaisesRegex(UnsafePortfolio,"Too many"):
            snapshot(Fake(covered,protective))

    def test_unprotected_tenth_position_blocks_all_new_entries(self):
        names=("BTC","ETH","SOL","XRP","DOGE","ADA","LINK","AVAX","DOT","LTC")
        positions=[]
        algos=[]
        for name in names:
            p=pos(name+"-USDT-SWAP")
            p["notionalUsd"]="100"
            positions.append(p)
            algos.append(algo(name+"-USDT-SWAP"))
        with self.assertRaisesRegex(UnsafePortfolio,"TP/SL"):
            snapshot(Fake(positions,algos[:-1]))
    def test_no_pending_orders(self):
        with self.assertRaisesRegex(UnsafePortfolio,"Outstanding"):
            snapshot(Fake(pending=[{"ordId":"123"}]))
    def test_over_limit_identifies_stop_risk_without_disclosing_balances(self):
        p=pos(); p["notionalUsd"]="2000"
        with self.assertRaises(RiskLimitExceeded) as ctx:
            snapshot(Fake([p],[algo(sl="97")]))
        self.assertEqual(ctx.exception.dimension, "STOP_RISK")
        self.assertEqual(str(ctx.exception), "Existing aggregate risk above permitted limits")

    def test_over_limit_identifies_isolated_margin(self):
        p=pos(); p["notionalUsd"]="12000"; p["lever"]="20"
        with self.assertRaises(RiskLimitExceeded) as ctx:
            snapshot(Fake([p],[algo(sl="99.9")]))
        self.assertEqual(ctx.exception.dimension, "ISOLATED_MARGIN")

    def test_both_risk_limits_report_both(self):
        p=pos(); p["notionalUsd"]="12000"; p["lever"]="20"
        with self.assertRaises(RiskLimitExceeded) as ctx:
            snapshot(Fake([p],[algo(sl="97")]))
        self.assertEqual(ctx.exception.dimension, "BOTH")

    def test_new_entries_leave_twenty_percent_risk_and_margin_headroom(self):
        self.assertEqual(NEW_ENTRY_CAP_FRACTION, Decimal("0.80"))
        s=snapshot(Fake([pos()],[algo()]))
        # 20 existing + 21 proposed stop risk: below 5% hard cap,
        # but above the 4% new-entry ceiling.
        with self.assertRaisesRegex(UnsafePortfolio,"stop risk"):
            check_new(s,Decimal("2100"),Decimal("0.01"))
        # Existing 100 plus new 305 margin: below the 50% hard
        # cap, but above the 40% new-entry ceiling.
        with self.assertRaisesRegex(UnsafePortfolio,"margin"):
            check_new(s,Decimal("6100"),Decimal("0.001"))
        self.assertEqual(sizing_equity(s),Decimal("800"))

    def test_limits_enforced(self):
        s=snapshot(Fake([pos()],[algo()]))
        with self.assertRaisesRegex(UnsafePortfolio,"stop risk"):
            check_new(s,Decimal("2000"),Decimal("0.02"))
        with self.assertRaisesRegex(UnsafePortfolio,"margin"):
            check_new(s,Decimal("9000"),Decimal("0.001"))
