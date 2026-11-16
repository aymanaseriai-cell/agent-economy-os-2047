"""Speed ranking is an uncalibrated public-data heuristic, never a trade guarantee."""
import copy
import time
import unittest
from trading.okx_live_executor import choose_signal


def candidate(symbol, hit=0.5, eta=30, rank=2.0):
    now = int(time.time() * 1000)
    return {
        "symbol": symbol, "quote_price": 100.0, "signal": "LONG",
        "last_complete_15m_candle_ms": now - 16 * 60 * 1000,
        "advanced_system_count": 7, "advanced_confirmations": 2,
        "advanced_veto_reasons": [], "derivatives_data_warnings": [],
        "execution": "DISABLED", "order_count": 0,
        "ordinal_buy_points": 5, "ordinal_sell_points": 0,
        "agents": [{"evidence": {}} for _ in range(5)] + [{"evidence": {
            "indicative_stop_not_an_order": 98,
            "indicative_target_not_an_order": 104}}],
        "omega_system_count": 10, "omega_veto_reasons": [],
        "omega_rank_score": rank, "omega_estimated_time_to_target_minutes": eta,
        "omega_target_hit_fraction_null_model": hit,
    }


class OmegaSpeedRankTests(unittest.TestCase):
    def test_fast_high_hit_candidate_wins(self):
        a = candidate("BTC-USDT-SWAP", hit=0.2, eta=120)
        b = candidate("ADA-USDT-SWAP", hit=0.8, eta=15)
        self.assertEqual(choose_signal({"results": [a, b]})["symbol"], b["symbol"])

    def test_uncertain_fast_candidate_not_automatically_preferred(self):
        a = candidate("BTC-USDT-SWAP", hit=0.95, eta=30)
        b = candidate("ADA-USDT-SWAP", hit=0.0, eta=15)
        self.assertEqual(choose_signal({"results": [a, b]})["symbol"], a["symbol"])

    def test_absent_probability_preserves_legacy_speed_rank(self):
        a = candidate("BTC-USDT-SWAP", eta=120, rank=2.1)
        b = candidate("ADA-USDT-SWAP", eta=15, rank=1.8)
        a.pop("omega_target_hit_fraction_null_model")
        b.pop("omega_target_hit_fraction_null_model")
        self.assertEqual(choose_signal({"results": [a, b]})["symbol"], b["symbol"])

    def test_invalid_probability_rejected(self):
        for val in ("NaN", "Infinity", -1, 1.1, "bad"):
            with self.subTest(value=val):
                a = candidate("BTC-USDT-SWAP", hit=val)
                self.assertIsNone(choose_signal({"results": [a]}))

    def test_omega_veto_unchanged(self):
        a = candidate("BTC-USDT-SWAP", hit=1.0, eta=1)
        a["omega_veto_reasons"] = ["adversarial_regime"]
        self.assertIsNone(choose_signal({"results": [a]}))


if __name__ == "__main__":
    unittest.main()
