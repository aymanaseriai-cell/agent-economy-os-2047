"""Quantum mathematical integrity / anti-overfitting checks, stdlib only."""
import math
import tempfile
import unittest
from pathlib import Path

from trading import titan_quantum_gate as q


def candles(n=140):
    rows = []
    for i in range(n):
        p = 100 + i * .05
        rows.append({"open": p, "high": p + .20,
                     "low": p - .20, "close": p + .01})
    return rows


def ordinary_case(end=4.15, trades=0, ruined=False, dd=0, hit=None):
    row = {"closed_equity_usdt": end, "closed_trades": trades,
           "max_drawdown_pct": dd, "ruin_happened": ruined}
    if hit is not None:
        row["hit_128"] = hit
    return row


def report(end=4.15, trades=0, classical_end=4.15):
    return {
        "start_usdt": 4.15, "goal_usdt": 9.462,
        "quantum_hardware_used": False, "real_orders": 0,
        "data": {"precommitted": True, "public_market_sha256": {"X-USDT-SWAP": "hash"}},
        "models": {
            "quantum": {p: {c: ordinary_case(end, trades, dd=10 if trades else 0)
                            for c in q.COSTS} for p in q.PERIODS},
            "classical": {p: {c: ordinary_case(classical_end, trades)
                              for c in q.COSTS} for p in q.PERIODS},
        },
    }


class QuantumGateTests(unittest.TestCase):
    def test_exact_goal(self):
        self.assertEqual(q.TARGET_USDT, 9.462)
        self.assertEqual(q.TARGET_MULTIPLIER, 2.28)

    def test_unitarity_and_born_bounds_varied_inputs(self):
        for x in (-3, -1, 0, 1, 3):
            for phase in q.PHASES:
                p = q.quantum_probability((x, -x / 2, x / 3), phase)
                self.assertTrue(0 <= p <= 1)

    def test_phase_ablation_and_identical_input_classical_control(self):
        features = (0.3, -0.8, 1.2)
        r = q.quantum_and_control(features)
        self.assertAlmostEqual(r["quantum_zero_phase"], q.quantum_probability(features, 0))
        self.assertAlmostEqual(r["classical"], q.classical_probability(features))
        self.assertFalse(r["quantum_hardware_used"])
        self.assertNotAlmostEqual(r["quantum"], r["quantum_zero_phase"], places=5)

    def test_inputs_and_phases_reject_nonfinite(self):
        with self.assertRaises(ValueError):
            q.quantum_probability((math.nan, 0, 0))
        with self.assertRaises(ValueError):
            q.quantum_probability((0, 0, 0), phase=float("inf"))
        with self.assertRaises(ValueError):
            q.classical_probability((1, 2))

    def test_future_bar_mutation_cannot_change_signal(self):
        rows = candles()
        a = q.completed_causal_features(rows, 120)
        future = [dict(x) for x in rows]
        future[121]["close"] = future[121]["high"]
        future[139]["high"] *= 5
        self.assertEqual(a, q.completed_causal_features(future, 120))
        self.assertEqual(q.quantum_and_control(a), q.quantum_and_control(
            q.completed_causal_features(future, 120)))

    def test_invalid_candles_fail_closed(self):
        rows = candles()
        rows[120]["close"] = -10
        with self.assertRaises(ValueError):
            q.completed_causal_features(rows, 120)

    def test_zero_trade_benchmark_no_profit(self):
        result = q.audit_closed_paper_report(report())
        self.assertEqual(result["verdict"], "NO_REPLICATED_128_EDGE_DO_NOT_DEPLOY")
        self.assertFalse(result["verified_live_plus128"])

    def test_unfilled_claimed_win_is_refused(self):
        with self.assertRaises(ValueError):
            q.audit_closed_paper_report(report(end=9.462, trades=0))

    def test_unrealized_hit_mismatch_is_refused(self):
        data = report()
        data["models"]["quantum"]["holdout_1"]["stress"]["hit_128"] = True
        with self.assertRaises(ValueError):
            q.audit_closed_paper_report(data)

    def test_both_costs_and_classical_comparator_required(self):
        data = report()
        del data["models"]["classical"]
        with self.assertRaises(ValueError):
            q.audit_closed_paper_report(data)
        data = report()
        del data["models"]["quantum"]["holdout_2"]["stress"]
        with self.assertRaises(ValueError):
            q.audit_closed_paper_report(data)

    def test_even_idealized_paper_candidate_not_called_real_profit(self):
        result = q.audit_closed_paper_report(report(end=9.5, trades=30))
        self.assertTrue(result["candidate_for_prospective_only"])
        self.assertFalse(result["verified_live_plus128"])
        self.assertEqual(result["verdict"], "PAPER_CANDIDATE_NOT_REAL_PROFIT")

    def test_stress_ruin_blocks_even_extreme_end_equity(self):
        data = report(end=10, trades=30)
        data["models"]["quantum"]["holdout_2"]["stress"]["ruin_happened"] = True
        self.assertFalse(q.audit_closed_paper_report(data)["candidate_for_prospective_only"])

    def test_ci_protocol_is_in_default_workflow(self):
        content = (Path(__file__).parents[1] /
                   ".github/workflows/ci.yml").read_text()
        self.assertIn("python -m trading.titan_quantum_gate --ci", content)
        self.assertIn("python -m unittest discover", content)

    def test_ci_run_does_not_claim_verified_return(self):
        result = q.run_selfcheck()
        self.assertFalse(result["historical_profit_proven"])
        self.assertFalse(result["live_profit_proven"])
        self.assertEqual(result["trade_orders_submitted"], 0)


if __name__ == "__main__":
    unittest.main()
