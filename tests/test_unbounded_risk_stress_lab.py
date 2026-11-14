"""Regression tests: unbounded-risk behavior is isolated to an offline study."""
import unittest
from trading.unbounded_risk_stress_lab import simulate, StressInputError


class UnboundedRiskStressTests(unittest.TestCase):
    def test_losses_can_exceed_100_percent_without_capping_negative_equity(self):
        study = simulate("100", [
            {"symbol": "SYNTH", "side": "long",
             "notional": "10000", "leverage": "100"}
        ], ["-0.05"])
        self.assertEqual(study["scenarios"][0]["hypothetical_equity_usdt"], "-400.00")
        self.assertEqual(study["scenarios"][0]["equity_change_pct"], "-500.00")
        self.assertTrue(study["scenarios"][0]["stress_insolvency"])
        self.assertEqual(study["orders_sent"], 0)
        self.assertFalse(study["live_trading_enabled"])
        self.assertFalse(study["market_or_private_api_access"])

    def test_no_limit_on_hypothetical_number_of_positions(self):
        positions = [
            {"symbol": "S" + str(i), "side": "short",
             "notional": "100000", "leverage": "200"}
            for i in range(30)
        ]
        study = simulate("100", positions, ["0.02"])
        self.assertEqual(study["hypothetical_position_count"], 30)
        self.assertTrue(study["hypothetical_margin_exceeds_equity"])
        self.assertEqual(study["risk_limits_enforced_on_simulated_positions"], False)
        self.assertLess(float(study["scenarios"][0]["hypothetical_equity_usdt"]), 0)

    def test_long_short_offsets_under_shared_shock(self):
        study = simulate("100", [
            {"symbol": "A", "side": "long", "notional": "1000", "leverage": "20"},
            {"symbol": "B", "side": "short", "notional": "1000", "leverage": "20"},
        ], ["-0.10", "0.10"])
        self.assertTrue(all(x["hypothetical_pnl_usdt"] == "0.00" for x in study["scenarios"]))

    def test_invalid_inputs_never_produce_a_report(self):
        valid = [{"symbol": "A", "side": "long", "notional": "100", "leverage": "10"}]
        for bad in [None, "NaN", "Infinity", "0", "-1"]:
            with self.assertRaises(StressInputError):
                simulate(bad, valid, ["0.01"])
        with self.assertRaises(StressInputError):
            simulate("100", valid, ["-1.01"])
        with self.assertRaises(StressInputError):
            simulate("100", [{"symbol": "X", "side": "long",
                               "notional": "5", "leverage": "NaN"}], ["0.01"])
        with self.assertRaises(StressInputError):
            simulate("100", [], ["0.01"])
        with self.assertRaises(StressInputError):
            simulate("100", valid, [])

    def test_no_live_executor_dependency(self):
        import trading.unbounded_risk_stress_lab as lab
        self.assertFalse(hasattr(lab, "OKX"))
        self.assertFalse(hasattr(lab, "execute"))


if __name__ == "__main__":
    unittest.main()
