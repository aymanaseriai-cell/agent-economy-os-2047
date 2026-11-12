import unittest
from decimal import Decimal
from trading.okx_dynamic_leverage import select_leverage
from trading.okx_live_executor import check_mode, contract_size, ExecutionBlocked
from trading.okx_portfolio_guard import check_new, UnsafePortfolio

class DynamicLeverageTests(unittest.TestCase):
    def test_upper_bound_is_reachable_on_tight_stops_only(self):
        self.assertEqual(select_leverage(".001", ".001", 125, 100), 100)
    def test_exchange_account_caps_override_strategy(self):
        self.assertEqual(select_leverage(".001", ".001", 100, 25), 25)
        self.assertIsNone(select_leverage(".001", ".001", 100, 9))
    def test_wider_stops_lower_leverage(self):
        tight = select_leverage(".001", ".001", 100, 100)
        wide = select_leverage(".015", ".001", 100, 100)
        self.assertTrue(10 <= wide < tight)
    def test_abstain_on_bad_stress_or_bad_input(self):
        self.assertIsNone(select_leverage(".10", ".01", 100, 100))
        for v in ("NaN", "-1", "Infinity"):
            with self.subTest(v=v), self.assertRaises(ValueError):
                select_leverage(v, ".001", 100, 100)
    def test_dynamic_mode_has_independent_arm(self):
        env = dict(OKX_ENABLE_REAL_TRADING="YES",
                   OKX_EXECUTION_ARM="I_ACCEPT_REAL_MONEY_LOSS",
                   OKX_STOP_CONTINUOUS="NO",
                   OKX_API_KEY="test",OKX_SECRET_KEY="test",OKX_PASSPHRASE="test",
                   OKX_LEVERAGE_MODE="dynamic")
        with self.assertRaisesRegex(ExecutionBlocked,"dynamic leverage arm"):
            check_mode("live",env)
        env["OKX_DYNAMIC_LEVERAGE_ARM"]="I_ACCEPT_VARIABLE_10_TO_100X_LIQUIDATION_RISK"
        check_mode("live",env)
    def test_dynamic_leverage_changes_position_sizing(self):
        inst = {"ctVal":"1","lotSz":"1","minSz":"1"}
        a = contract_size(inst,100,1000,Decimal(".001"),
                          capital_mode="adaptive_guarded",exchange_max=10000,leverage=20)
        b = contract_size(inst,100,1000,Decimal(".001"),
                          capital_mode="adaptive_guarded",exchange_max=10000,leverage=100)
        self.assertGreaterEqual(b,a)
    def test_aggregate_margin_checks_actual_leverage(self):
        snap={"total":Decimal("1000"),"planned":Decimal("0"),
              "notional":Decimal("3000"),"margin_used":Decimal("300"),
              "free":Decimal("500")}
        check_new(snap,Decimal("1000"),Decimal(".001"),leverage=100)
        with self.assertRaisesRegex(UnsafePortfolio,"margin"):
            check_new(snap,Decimal("25000"),Decimal(".0001"),leverage=100)

if __name__ == "__main__":
    unittest.main()
