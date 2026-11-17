"""Independent market replication does not change original Q6 signals."""
import unittest
from trading import titan_q6_4h_swing_128 as q6
from trading import titan_q6_replication_128 as r

class Replication(unittest.TestCase):
    def test_strict_nonoverlap_prior_research_markets(self):
        self.assertTrue(q6.UNIVERSE)
        self.assertGreaterEqual(len(r.ALLOWED),6)
        self.assertTrue(r.ALLOWED.isdisjoint(r.PREVIOUS_BASKETS))
        self.assertTrue(r.ALLOWED.isdisjoint(q6.FORBIDDEN))
    def test_original_target_and_rules_are_unaltered(self):
        self.assertEqual((q6.START,q6.TARGET),(4.15,9.462))
        self.assertEqual(q6.LEVERAGES,(3.,10.))
        self.assertEqual(q6.BLOCK,16)
        self.assertEqual(q6.PROFIT_ATR,7.)
        self.assertEqual(q6.STOP_ATR,1.9)
        self.assertEqual(q6.TRAIL_ATR,2.1)
        self.assertEqual(q6.MAX_HOLD_15M,640)
    def test_study_hash_distinct_from_original(self):
        self.assertNotEqual(r.REPLICATION_ID,q6.STUDY)
    def test_no_order_execution_code(self):
        from pathlib import Path
        s=(Path(__file__).parents[1]/"trading/titan_q6_replication_128.py").read_text()
        self.assertNotIn("OKX_API_KEY",s)
        self.assertNotIn("/api/v5/trade/order",s)
        self.assertIn("q6.evaluate(markets,specs,sha)",s)

if __name__=="__main__":
    unittest.main()
