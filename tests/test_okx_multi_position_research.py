import unittest
from trading.okx_multi_position_research import plan, eligible, PlanningError


def signal(symbol="BTC-USDT-SWAP", score=0.2, direction="LONG"):
    return {"symbol": symbol, "signal": direction,
            "quote_price": 100, "omega_rank_score": score,
            "omega_system_count": 10, "omega_veto_reasons": [],
            "advanced_system_count": 7, "advanced_confirmations": 2,
            "advanced_veto_reasons": [], "derivatives_data_warnings": [],
            "agents": [{"evidence": {}} for _ in range(5)] +
                      [{"evidence": {"indicative_stop_not_an_order":
                                     99 if direction == "LONG" else 101,
                                     "indicative_target_not_an_order":
                                     102 if direction == "LONG" else 98}}]}


def report(*items):
    return {"mode": "SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY",
            "results": list(items), "errors": []}


class MultiPositionResearchTests(unittest.TestCase):
    def test_two_symbols_are_hypothetically_fully_allocated_without_order(self):
        x = plan(report(signal(), signal("ETH-USDT-SWAP", .3)))
        self.assertEqual(x["status"], "HYPOTHETICAL_ONLY_NOT_SAFE_TO_AUTO_EXECUTE")
        self.assertEqual(x["orders_sent"], 0)
        self.assertFalse(x["live_trading_enabled"])
        self.assertAlmostEqual(sum(i["margin_fraction_of_total_equity"]
                                   for i in x["positions"]), 1.0)
        self.assertEqual(x["gross_notional_multiple_of_equity"], 20)
        self.assertEqual(x["stress_equity_loss_5pct_adverse_move_pct_before_fees"], 100)

    def test_no_auto_trade_with_only_one_qualified_coin(self):
        x = plan(report(signal()))
        self.assertEqual(x["status"], "NO_HYPOTHETICAL_PLAN")
        self.assertEqual(x["orders_sent"], 0)

    def test_never_promote_vetoed_coin(self):
        invalid = signal("ETH-USDT-SWAP", .5)
        invalid["omega_veto_reasons"] = ["volatility"]
        self.assertFalse(eligible(invalid))
        self.assertEqual(plan(report(signal(), invalid))["eligible_symbols"], 1)

    def test_distinct_symbols_only(self):
        self.assertEqual(plan(report(signal(), signal(score=.8)))["eligible_symbols"], 1)

    def test_long_short_vetted(self):
        x = plan(report(signal(), signal("ETH-USDT-SWAP", .3, "SHORT")))
        self.assertEqual(len(x["positions"]), 2)

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaises(PlanningError):
            plan({"mode": "wrong", "results": [], "errors": []})
        with self.assertRaises(PlanningError):
            plan(report(signal(),signal("ETH-USDT-SWAP")),leverage=50)
        with self.assertRaises(PlanningError):
            plan(report(signal(),signal("ETH-USDT-SWAP")),slots=1)

    def test_scan_error_blocks_planner(self):
        with self.assertRaises(PlanningError):
            plan({"mode":"SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY",
                  "errors":["bad feed"],"results":[]})


if __name__ == "__main__":
    unittest.main()
