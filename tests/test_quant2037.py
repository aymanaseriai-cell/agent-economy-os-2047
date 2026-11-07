import unittest
from trading.quant2037 import (
    jump_sentinel, permutation_entropy, variance_ratio, value_migration,
    depth_fragility, flow_acceleration, counterfactual_stability, evaluate_advanced,
)


def bars(n=200, move=0.0):
    return [{"ts": i * 900000, "open": 100.0 + i * move,
             "high": (100 + i * move) * 1.003, "low": (100 + i * move) * .997,
             "close": 100.0 + i * move, "quote_vol": 10000.0}
            for i in range(n)]


def book():
    return {"bids": [["100", "12", "0", "1"] for _ in range(20)],
            "asks": [["101", "10", "0", "1"] for _ in range(20)]}


def trades():
    return ([{"ts": str(i), "side": "sell", "sz": "20"} for i in range(60)] +
            [{"ts": str(i), "side": "buy", "sz": "20"} for i in range(60, 120)])


def core(signal="LONG"):
    roles = ["02_auction_cartographer", "03_tape_detective",
             "04_derivatives_intelligence", "05_structure_navigator"]
    return {"signal": signal, "agents": [{"agent": a, "vote": 1, "strength": 2} for a in roles]}


class Quant2037Tests(unittest.TestCase):
    def test_all_seven_execute_without_exchange(self):
        result = evaluate_advanced(bars(move=.05), book(), trades(), core())
        self.assertEqual(result["advanced_system_count"], 7)
        self.assertEqual(len({x["system"] for x in result["advanced_systems"]}), 7)
        self.assertEqual(result["order_count"], 0)
        self.assertEqual(result["execution"], "DISABLED")

    def test_no_signal_created_from_wait(self):
        result = evaluate_advanced(bars(move=.05), book(), trades(), core("WAIT"))
        self.assertEqual(result["signal"], "WAIT")

    def test_insufficient_history_raises_and_fails_closed(self):
        with self.assertRaises(ValueError):
            value_migration(bars(100))

    def test_jump_detects_extreme_close(self):
        arr = bars()
        arr[-1]["close"] = 125.0
        self.assertEqual(jump_sentinel(arr)["risk"], "VETO")

    def test_permutation_entropy_bounded(self):
        p = permutation_entropy(bars(move=.05))
        self.assertTrue(0 <= p["metrics"]["normalized_entropy"] <= 1)

    def test_variance_ratio_stable(self):
        self.assertAlmostEqual(variance_ratio(bars())["metrics"]["variance_ratio_4"], 1)

    def test_migration_structure(self):
        result = value_migration(bars(move=.1))
        self.assertGreater(result["metrics"]["poc_shift_bp"], 0)

    def test_shallow_book_veto(self):
        self.assertEqual(depth_fragility({"bids": [], "asks": []})["risk"], "VETO")

    def test_accelerating_buy_flow(self):
        self.assertEqual(flow_acceleration(trades())["vote"], 1)

    def test_counterfactual_four_knockouts(self):
        s = counterfactual_stability(core("LONG"))
        self.assertEqual(s["metrics"]["leave_one_out_survivals"], 4)

    def test_no_confirmation_means_wait(self):
        # No migration, no VR, no entropy vote, no recent positive delta.
        flat_trades = [{"ts": str(i), "side": "buy" if i % 2 == 0 else "sell", "sz": "1"}
                       for i in range(100)]
        result = evaluate_advanced(bars(), book(), flat_trades, core("LONG"))
        self.assertEqual(result["signal"], "WAIT")
        self.assertIn("no_independent_quant_confirmation", result["advanced_veto_reasons"])

    def test_one_veto_overrides_positive_confirmation(self):
        result = evaluate_advanced(bars(move=.05), {"bids": [], "asks": []}, trades(), core())
        self.assertEqual(result["signal"], "WAIT")
        self.assertTrue(any("depth_fragility" in s for s in result["advanced_veto_reasons"]))


if __name__ == "__main__":
    unittest.main()
