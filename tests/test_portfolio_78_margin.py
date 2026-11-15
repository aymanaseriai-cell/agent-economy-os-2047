"""Regression checks for aggregate isolated margin cap; never executes real orders."""
import unittest
from decimal import Decimal
from trading.okx_portfolio_guard import MARGIN_CAP, MAX_POSITIONS, UnsafePortfolio, check_new

class Portfolio78MarginTests(unittest.TestCase):
    def test_policy_values(self):
        self.assertEqual(MAX_POSITIONS, 25)  # Monitor legacy accounts; workflow limits entries to 3.
        self.assertEqual(MARGIN_CAP, Decimal("0.78"))

    def test_new_trade_over_78_percent_margin_is_rejected(self):
        snap = {"total": Decimal("9"), "planned":Decimal("0"),
                "margin_used":Decimal("6.53"), "notional":Decimal("0")}
        # 10 USDT new notional at 20x adds 0.50 USDT margin.
        with self.assertRaisesRegex(UnsafePortfolio, "margin"):
            check_new(snap, Decimal("10"), Decimal("0.01"), leverage=Decimal("20"))

    def test_exact_78_percent_margin_boundary_is_accepted(self):
        snap = {"total": Decimal("9"), "planned":Decimal("0"),
                "margin_used":Decimal("6.52"), "notional":Decimal("0")}
        check_new(snap, Decimal("10"), Decimal("0.01"), leverage=Decimal("20"))

    def test_planned_stop_risk_gate_is_retained(self):
        snap = {"total": Decimal("9"), "planned":Decimal("8.90"),
                "margin_used":Decimal("0"), "notional":Decimal("0")}
        with self.assertRaisesRegex(UnsafePortfolio, "stop risk"):
            check_new(snap, Decimal("10"), Decimal("0.01"), leverage=Decimal("20"))

if __name__ == "__main__":
    unittest.main()
