"""Checks for Q6 locked out-of-cohort three-holdout replication."""
import unittest, math, copy
from trading import titan_q6_repeatability_proof as p
from trading import titan_q6_4h_swing_128 as q6

class Q6Proof(unittest.TestCase):
    def test_fingerprint_stays_identical(self):
        self.assertTrue(p.validate_original_model())
        self.assertEqual(len(p.ORIGINAL_Q6_BLOB_SHA),40)
    def test_only_one_locked_primary(self):
        self.assertEqual((p.PRIMARY,p.LEV),("q6_coherent_breakout",10.))
        self.assertNotIn(p.PRIMARY,p.DIAGNOSTIC)
        self.assertEqual((p.START,p.GOAL,p.TARGET_PCT),(4.15,9.462,128.))
        self.assertEqual(p.COSTS,("ordinary","stress"))
    def test_nonoverlap_and_precommitted_named_market_universe(self):
        self.assertGreater(len(p.CANDIDATES-p.EXCLUDED),p.N)
        self.assertTrue(p.EXCLUDED.issuperset({
            "BLUR","MINA","ZIL","STX","DYDX","JTO","XTZ","AXS","CFX","NMR"
        }))
        self.assertFalse("BTC" in p.CANDIDATES-p.EXCLUDED)
    def test_separate_complete_holdouts(self):
        a=p.periods(180*96-1)
        self.assertEqual(a["train"][1],a["holdout_1"][0])
        self.assertEqual(a["holdout_1"][1],a["holdout_2"][0])
        self.assertEqual(a["holdout_2"][1],a["holdout_3"][0])
        self.assertEqual(a["holdout_3"][1],180*96-1)
        self.assertEqual(a["combined_holdout"],
                         (a["holdout_1"][0],a["holdout_3"][1]))
    def test_fake_period_too_short_is_rejected(self):
        with self.assertRaises(ValueError):p.periods(10000)
    def test_data_panel_cannot_be_missing(self):
        with self.assertRaises(ValueError):
            p.replay({}, {}, {})
    def test_no_funded_account_access(self):
        from pathlib import Path
        code=(Path(__file__).parents[1]/"trading/titan_q6_repeatability_proof.py").read_text()
        self.assertNotIn("OKX_API_KEY",code)
        self.assertNotIn("/api/v5/trade/order",code)
        self.assertIn('"primary_proof_gate_pass"',code)
    def test_binary_replay_does_not_override_original_source(self):
        self.assertEqual(
            p.git_blob_sha(__import__("pathlib").Path(q6.__file__).read_bytes()),
            p.ORIGINAL_Q6_BLOB_SHA)

if __name__=="__main__": unittest.main()
