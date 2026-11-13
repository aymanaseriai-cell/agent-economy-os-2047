import unittest
from trading.titan2037_sentinels import AGENTS, DAY_MS, HOUR_MS, audit

BASE = 30 * DAY_MS

def episode(i, **updates):
    e = {"decision_id": f"d{i}", "symbol": f"COIN{i % 10}-USDT-SWAP",
         "side": "LONG", "decision_ms": BASE + i * 4 * HOUR_MS,
         "outcome_ms": BASE + i * 4 * HOUR_MS + HOUR_MS,
         "entry": "100", "forward_exit": "101", "fee_bp": "8",
         "slippage_bp": "4", "funding_bp": "1", "vetoes": ["omega_veto"],
         "regime": "RANGE", "regime_feature": i / 100}
    e.update(updates)
    return e

def pack(episodes, now=None):
    return {"as_of_ms": now or BASE + 500 * 4 * HOUR_MS, "episodes": episodes}

class TitanSentinelTests(unittest.TestCase):
    def test_missing_evidence_no_fabricated_profits(self):
        x = audit({"as_of_ms": 0, "episodes": []})
        self.assertEqual(set(x["agents"]), set(AGENTS))
        self.assertEqual(x["agents"]["governance_council"]["status"],
                         "INSUFFICIENT_PROSPECTIVE_EVIDENCE")
        self.assertIsNone(x["agents"]["cost_reality"]["mean_hypothetical_net_bp"])
        self.assertEqual(x["orders"], 0)
        self.assertFalse(x["live_trading_reenabled"])
        self.assertFalse(x["verified_against_private_exchange"])

    def test_short_costs_subtracted_correctly(self):
        x = audit(pack([episode(1, side="SHORT", forward_exit="99")]))
        self.assertAlmostEqual(x["agents"]["cost_reality"]["mean_hypothetical_net_bp"], 87)

    def test_funding_credit_can_improve_not_prove(self):
        x = audit(pack([episode(1, funding_bp="-3")]))
        self.assertAlmostEqual(x["agents"]["cost_reality"]["mean_hypothetical_net_bp"], 91)

    def test_duplicate_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate decision"):
            audit(pack([episode(1), episode(1)]))

    def test_repeated_symbol_four_hour_bucket_collapses(self):
        a = episode(1)
        b = episode(1, decision_id="second",
                    decision_ms=a["decision_ms"] + 1000,
                    outcome_ms=a["outcome_ms"] + 1000)
        x = audit(pack([a, b]))
        self.assertEqual(x["agents"]["independence_graph"]["distinct_symbol_4h_clusters"], 1)
        self.assertEqual(x["agents"]["independence_graph"]["repeated_signals_excluded"], 1)

    def test_future_outcome_rejected(self):
        e = episode(1, outcome_ms=BASE+600*4*HOUR_MS)
        with self.assertRaisesRegex(ValueError, "future"):
            audit(pack([e]))

    def test_timestamp_equal_rejected(self):
        e = episode(1)
        e["outcome_ms"] = e["decision_ms"]
        with self.assertRaises(ValueError):
            audit(pack([e]))

    def test_unconfirmed_veto_not_imported(self):
        with self.assertRaises(ValueError):
            audit(pack([episode(1, vetoes=[])]))

    def test_invalid_prices_and_costs(self):
        for alteration in ({"entry":"0"}, {"forward_exit":"NaN"},
                           {"fee_bp":-1}, {"slippage_bp":"Infinity"},
                           {"funding_bp":501}, {"regime_feature":"1e999"}):
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                audit(pack([episode(1, **alteration)]))

    def test_status_with_few_data(self):
        x = audit(pack([episode(i) for i in range(20)]))
        self.assertEqual(x["agents"]["governance_council"]["status"],
                         "INSUFFICIENT_PROSPECTIVE_EVIDENCE")
        self.assertIsNotNone(x["agents"]["tail_shield"]["worst_tail_mean_net_bp"])
        self.assertIsNone(x["agents"]["uncertainty_guard"]["holdout_bootstrap_5pct_mean_bp"])

    def test_sufficient_evidence_still_never_arms(self):
        x = audit(pack([episode(i, regime_feature=0.2) for i in range(130)]))
        self.assertEqual(x["agents"]["governance_council"]["status"],
                         "HUMAN_REVIEW_REQUIRED_NOT_PROFIT_PROOF")
        self.assertIsNotNone(x["agents"]["uncertainty_guard"]["holdout_bootstrap_5pct_mean_bp"])
        self.assertEqual(x["orders"], 0)
        self.assertFalse(x["agents"]["governance_council"]["automatic_live_approval"])

    def test_drift_requires_review(self):
        vals = [episode(i, regime_feature=0 if i<90 else 100) for i in range(130)]
        x = audit(pack(vals))
        self.assertEqual(x["agents"]["regime_drift_radar"]["status"], "REVIEW_DRIFT")
        self.assertEqual(x["agents"]["governance_council"]["status"],
                         "REVIEW_DRIFT_NO_AUTOMATIC_APPROVAL")

    def test_purged_train_avoids_future_outcomes(self):
        vals = [episode(i, outcome_ms=episode(i)["decision_ms"]+2*DAY_MS)
                for i in range(120)]
        x = audit(pack(vals))
        self.assertLess(x["agents"]["regime_drift_radar"]["purged_train"], 84)

    def test_determinism_independent_of_input_order(self):
        es = [episode(i) for i in range(130)]
        a = audit(pack(es))
        b = audit(pack(list(reversed(es))))
        self.assertEqual(a, b)

    def test_symbol_or_side_or_timestamp_rejected(self):
        for change in ({"side":"WAIT"}, {"symbol":""},
                       {"decision_ms":True}, {"outcome_ms":-1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit(pack([episode(1, **change)]))

    def test_no_private_order_routes_in_source(self):
        import inspect
        import trading.titan2037_sentinels as m
        src = inspect.getsource(m)
        for forbidden in ("OKX_API_KEY", "OKX_SECRET_KEY", "/api/v5/trade/order",
                          "requests.post(", "urlopen(", "subprocess.run("):
            self.assertNotIn(forbidden, src)

if __name__ == "__main__":
    unittest.main()
