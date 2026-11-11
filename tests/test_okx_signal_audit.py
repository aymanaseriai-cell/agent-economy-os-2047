"""Unit tests for public-only TITAN decision-funnel telemetry."""
import unittest
from trading.okx_signal_audit import audit_report, markdown_summary


def example(symbol, direction, *, adv=(), omega=(), confirmed=1,
            net=-250.0, score=0, final="WAIT"):
    return {
        "symbol": symbol,
        "signal": final,
        "core_signal_before_advanced": direction,
        "advanced_confirmations": confirmed,
        "advanced_veto_reasons": list(adv),
        "derivatives_data_warnings": [],
        "omega_veto_reasons": list(omega),
        "omega_system_count": 10,
        "omega_rank_score": score,
        "omega_systems": [{
            "evidence": {"net_expectation_bp_null_model": net}
        }],
    }


class AuditTests(unittest.TestCase):
    def report(self):
        records = [
            example("A-USDT-SWAP", "WAIT"),
            example("B-USDT-SWAP", "LONG",
                    adv=["no_independent_quant_confirmation"], confirmed=0),
            example("C-USDT-SWAP", "SHORT",
                    omega=["multiverse_no_positive_net_edge"]),
            example("D-USDT-SWAP", "LONG", net=25., score=1., final="LONG"),
        ]
        return {
            "mode": "SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY",
            "market_scan_complete": True, "errors": [],
            "markets_analyzed": 4, "markets_screened_for_liquidity": 227,
            "utc_timestamp": "2026-11-11T19:00:00Z",
            "actionable_research_labels": 1,
            "results": records,
        }

    def test_counts_real_gates_in_order(self):
        stats = audit_report(self.report())
        self.assertEqual(stats["20x_crypto_contracts_screened"], 227)
        self.assertEqual(stats["core_candidates"], 3)
        self.assertEqual(stats["passed_independent_quant"], 2)
        self.assertEqual(stats["passed_omega_and_research"], 1)
        self.assertEqual(stats["advanced_veto_counts"],
                         {"no_independent_quant_confirmation": 1})
        self.assertEqual(stats["omega_veto_counts_after_quant"],
                         {"multiverse_no_positive_net_edge": 1})
        excluded = next(x for x in stats["candidate_evidence"]
                        if x["symbol"] == "B-USDT-SWAP")
        self.assertEqual(excluded["omega_vetoes"],
                         ["NOT_EVALUATED_ON_REJECTED_DIRECTION"])
        self.assertIsNone(excluded["omega_null_model_net_bp"])
        self.assertIn("NO ORDERS", markdown_summary(stats))
        self.assertTrue(stats["no_orders_placed_by_this_audit"])

    def test_partial_scan_and_data_errors_cannot_masquerade_as_success(self):
        value = self.report()
        value["errors"] = [{"symbol": "X", "reason": "network failure"}]
        with self.assertRaises(ValueError):
            audit_report(value)
        value["errors"] = []
        value["market_scan_complete"] = False
        with self.assertRaises(ValueError):
            audit_report(value)

    def test_inconsistent_final_acceptance_is_rejected(self):
        value = self.report()
        value["actionable_research_labels"] = 3
        with self.assertRaises(ValueError):
            audit_report(value)


if __name__ == "__main__":
    unittest.main()
