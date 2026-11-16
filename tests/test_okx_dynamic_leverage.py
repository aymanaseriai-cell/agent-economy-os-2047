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
        self.assertIsNone(select_leverage(".001", ".001", 100, 19))
        self.assertEqual(select_leverage(".001", ".001", 100, 20), 20)
    def test_wider_stops_lower_leverage(self):
        tight = select_leverage(".001", ".001", 100, 100)
        wide = select_leverage(".010", ".001", 100, 100)
        self.assertTrue(20 <= wide < tight)
        self.assertIsNone(select_leverage(".015", ".001", 100, 100))
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
            check_new(snap,Decimal("70001"),Decimal(".0001"),leverage=100)

if __name__ == "__main__":
    unittest.main()


class ExchangeMaximumLeverageTests(unittest.TestCase):
    """No live orders: explicitly confirmed, account-and-instrument ceilings."""

    def test_selects_highest_verified_for_each_instrument(self):
        from trading.okx_dynamic_leverage import select_exchange_max_leverage
        self.assertEqual(select_exchange_max_leverage("125", "200"), Decimal("125"))
        self.assertEqual(select_exchange_max_leverage("150", "75"), Decimal("75"))
        self.assertEqual(select_exchange_max_leverage("50", "50"), Decimal("50"))
        self.assertEqual(select_exchange_max_leverage("5.5", "8"), Decimal("5.5"))

    def test_missing_or_anomalous_caps_refuse(self):
        from trading.okx_dynamic_leverage import select_exchange_max_leverage
        for raw in ("", "NaN", "Infinity", "0", "-2", "1001", None):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                select_exchange_max_leverage(raw, "125")
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                select_exchange_max_leverage("125", raw)

    def test_separate_max_leverage_authorization_is_mandatory(self):
        from trading.okx_live_executor import EXCHANGE_MAX_LEVERAGE_ARM
        env = dict(OKX_ENABLE_REAL_TRADING="YES",
                   OKX_EXECUTION_ARM="I_ACCEPT_REAL_MONEY_LOSS",
                   OKX_STOP_CONTINUOUS="NO",
                   OKX_API_KEY="test", OKX_SECRET_KEY="test", OKX_PASSPHRASE="test",
                   OKX_LEVERAGE_MODE="exchange_max",
                   OKX_DYNAMIC_LEVERAGE_ARM="I_ACCEPT_VARIABLE_10_TO_100X_LIQUIDATION_RISK")
        with self.assertRaisesRegex(ExecutionBlocked, "maximum leverage confirmation"):
            check_mode("live", env)
        env["OKX_EXCHANGE_MAX_LEVERAGE_ARM"] = EXCHANGE_MAX_LEVERAGE_ARM
        check_mode("live", env)

    def test_above_100x_sizing_obeys_lot_and_existing_stop_veto(self):
        from trading.okx_live_executor import OpportunityRiskRejected
        inst = {"ctVal":"1", "lotSz":"1", "minSz":"1"}
        quantity = contract_size(inst, "1", "1000", ".001",
                                 capital_mode="margin_9999", exchange_max="500000", leverage="125")
        self.assertEqual(quantity, Decimal("124987"))
        with self.assertRaises(OpportunityRiskRejected):
            contract_size(inst, "1", "1000", ".01", capital_mode="margin_9999",
                          exchange_max="500000", leverage="125")
