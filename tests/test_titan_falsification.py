import json
import math
import unittest

from trading.titan_falsification import falsify_edge


def rows(n=210, slope=0.0005, wave=0.001):
    series = []
    for i in range(n):
        close = 100 * math.exp(i * slope + wave * math.sin(i / 4))
        op = close * (1 - 0.00025)
        series.append({"ts": 900000 * i, "open": op,
                       "high": close * 1.003, "low": op * .997,
                       "close": close, "quote_vol": 50000 + (i % 9) * 100})
    return series


class FalsificationTests(unittest.TestCase):
    def test_deterministic_three_fold_research_no_orders(self):
        audit = falsify_edge(rows())
        self.assertTrue(audit["data_valid"])
        self.assertTrue(audit["research_only"])
        self.assertFalse(audit["can_trade_live"])
        self.assertEqual(audit["orders_placed"], 0)
        self.assertEqual(len(audit["folds"]), 3)
        self.assertEqual(audit, falsify_edge(rows()))
        json.dumps(audit)
        for f in audit["folds"]:
            self.assertLess(f["train_end_exclusive"], f["test_start_signal"])
            self.assertLess(f["test_start_signal"], f["test_end_exclusive"])

    def test_experiment_is_resilient_to_unseen_future_mutations(self):
        baseline = falsify_edge(rows())
        modified = rows()
        # Everything after first heldout window cannot affect its selected model.
        end_first = baseline["folds"][0]["test_end_exclusive"]
        for i in range(end_first + 1, len(modified)):
            p = modified[i]["close"] * (1.05 if i % 2 else .95)
            modified[i]["open"] = p
            modified[i]["close"] = p
            modified[i]["high"] = p * 1.01
            modified[i]["low"] = p * .99
        alternate = falsify_edge(modified)
        self.assertEqual(baseline["folds"][0]["selected"],
                         alternate["folds"][0]["selected"])
        self.assertEqual(baseline["folds"][0]["training"],
                         alternate["folds"][0]["training"])
        self.assertEqual(baseline["folds"][0]["holdout"],
                         alternate["folds"][0]["holdout"])

    def test_adverse_cost_stress_never_improves_same_holdout_trades(self):
        a = falsify_edge(rows())
        if a["out_of_sample_trades"] > 0:
            p = a["stress_net_sum_pct"]
            self.assertGreaterEqual(p["1x"], p["2x"])
            self.assertGreaterEqual(p["2x"], p["4x"])

    def test_flat_market_cannot_fake_statistical_significance(self):
        audit = falsify_edge(rows(slope=0, wave=0))
        self.assertEqual(audit["out_of_sample_trades"], 0)
        self.assertIsNone(audit["circular_shift_null_tail_fraction"])
        self.assertEqual(audit["status"], "INSUFFICIENT_EVIDENCE")

    def test_corrupted_and_short_history_fails_closed(self):
        self.assertFalse(falsify_edge(rows(150))["data_valid"])
        b = rows()
        b[70]["close"] = -1
        self.assertFalse(falsify_edge(b)["data_valid"])
        self.assertFalse(falsify_edge(rows(), slippage_bp_per_side=-1)["data_valid"])

    def test_null_fraction_is_bounded_not_an_authorization(self):
        audit = falsify_edge(rows(n=420, slope=0.001, wave=0.003))
        p = audit["circular_shift_null_tail_fraction"]
        if p is not None:
            self.assertGreaterEqual(p, 0)
            self.assertLessEqual(p, 1)
        self.assertFalse(audit["can_trade_live"])


if __name__ == "__main__":
    unittest.main()
