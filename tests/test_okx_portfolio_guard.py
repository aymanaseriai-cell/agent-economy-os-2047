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
    def test_missing_position_amount_is_unknown_not_flat(self):
        with self.assertRaisesRegex(UnsafePortfolio, "Unverifiable position row"):
            snapshot(Fake(positions=[{"instId": "BTC-USDT-SWAP"}]))

    def test_missing_actual_leverage_is_not_replaced_with_default(self):
        with self.assertRaisesRegex(UnsafePortfolio, "leverage missing"):
            snapshot(Fake([pos()], [algo()]), require_position_leverage=True)

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
        p=pos(); p["notionalUsd"]="20000"; p["lever"]="100"
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
        p=pos(); p["notionalUsd"]="20000"; p["lever"]="20"
        with self.assertRaises(RiskLimitExceeded) as ctx:
            snapshot(Fake([p],[algo(sl="97")]))
        self.assertEqual(ctx.exception.dimension, "BOTH")

    def test_new_entries_use_exactly_fifty_percent_aggregate_budget(self):
        from trading.okx_portfolio_guard import RISK_CAP, MARGIN_CAP
        self.assertEqual(RISK_CAP, Decimal("0.50"))
        self.assertEqual(MARGIN_CAP, Decimal("0.50"))
        self.assertEqual(NEW_ENTRY_CAP_FRACTION, Decimal("1.00"))
        s=snapshot(Fake([pos()],[algo()]))
        # Stop risk: 20 existing + 480 proposed equals 500 (50% of equity).
        check_new(s,Decimal("48000"),Decimal("0.01"),leverage=Decimal("100"))
        with self.assertRaisesRegex(UnsafePortfolio,"stop risk"):
            check_new(s,Decimal("48001"),Decimal("0.01"),leverage=Decimal("100"))
        # Isolated margin: 100 existing + 400 proposed equals 500.
        check_new(s,Decimal("8000"),Decimal("0.001"))
        with self.assertRaisesRegex(UnsafePortfolio,"margin"):
            check_new(s,Decimal("8001"),Decimal("0.001"))
        self.assertEqual(sizing_equity(s),Decimal("800"))

    def test_limits_enforced(self):
        s=snapshot(Fake([pos()],[algo()]))
        with self.assertRaisesRegex(UnsafePortfolio,"stop risk"):
            check_new(s,Decimal("25000"),Decimal("0.02"))
        with self.assertRaisesRegex(UnsafePortfolio,"margin"):
            check_new(s,Decimal("9000"),Decimal("0.001"))
