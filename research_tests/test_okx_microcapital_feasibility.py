import unittest
from decimal import Decimal
from trading.okx_microcapital_feasibility import evaluate, minimum_notional, positive_decimal

def instrument(**overrides):
    value = {"instId": "BTC-USDT-SWAP", "state": "live", "settleCcy": "USDT",
             "ctValCcy": "BTC", "minSz": "0.01", "lotSz": "0.01", "ctVal": "0.001"}
    value.update(overrides)
    return value

class TinyEquityFeasibility(unittest.TestCase):
    def test_guarded_budget(self):
        r = evaluate([instrument()], [{"instId": "BTC-USDT-SWAP", "last": "60000"}], equity="4.14")
        self.assertEqual(Decimal(r["max_notional_budget_usdt"]), Decimal("0.8280"))
        self.assertEqual(r["preliminarily_within_budget"], 1)
        self.assertEqual(Decimal(r["closest"][0]["min_notional_usdt"]), Decimal("0.60000"))

    def test_exceeds_budget(self):
        r = evaluate([instrument(minSz="0.1", lotSz="0.1")],
                     [{"instId": "BTC-USDT-SWAP", "last": "60000"}], equity="4.14")
        self.assertEqual(r["preliminarily_within_budget"], 0)

    def test_round_up_to_lot(self):
        self.assertEqual(minimum_notional(instrument(minSz="0.013"), "60000"),
                         Decimal("1.20000"))

    def test_reject_unsupported_and_invalid(self):
        self.assertIsNone(minimum_notional(instrument(ctValCcy="USDT"), "60000"))
        self.assertIsNone(minimum_notional(instrument(), "0"))
        with self.assertRaises(ValueError):
            positive_decimal("NaN")

if __name__ == "__main__":
    unittest.main()
