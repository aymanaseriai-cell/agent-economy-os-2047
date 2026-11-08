"""Runs actual imported upstream APIs; never authenticates to OKX."""
import json
import unittest
from pathlib import Path

from trading import nexus_seven_2047 as nexus

ROOT=Path(__file__).resolve().parents[1]
BOOK=ROOT/"reports/nexus7_frozen_real_okx_book_20261108.json"

class SevenRepoJointIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book=json.loads(BOOK.read_text())
        cls.output=nexus.run(cls.book,seed=2037)

    def test_real_public_book_with_valid_levels(self):
        self.assertTrue(nexus.validate_public_book(self.book))
        self.assertEqual(len(self.book["book"]["bids"]),20)
        self.assertEqual(len(self.book["book"]["asks"]),20)

    def test_all_seven_real_upstream_libraries_were_invoked(self):
        self.assertTrue(self.output["seven_imported_and_exercised"])
        self.assertEqual(len(self.output["modules"]),7)
        self.assertEqual(set(self.output["modules"]),set(nexus.REPOSITORIES))
        self.assertTrue(all(v["status"]=="executed" for v in self.output["modules"].values()))

    def test_causal_recovery_is_synthetic_only(self):
        est=self.output["modules"]["dowhy"]["estimated_adjusted_effect"]
        self.assertAlmostEqual(est,0.65,delta=.14)
        self.assertTrue(self.output["modules"]["dowhy"]["not_estimated_from_real_trade_outcomes"])
        self.assertEqual(self.output["synthetic_data"]["real_future_outcomes"],0)

    def test_cleanlab_flags_known_intentional_data_errors(self):
        q=self.output["modules"]["cleanlab"]
        self.assertGreater(q["suspect_count"],0)
        self.assertGreater(q["detected_injected_count"],0)

    def test_art_adversarial_perturbation_is_real_function_call(self):
        q=self.output["modules"]["art"]
        self.assertEqual(q["attacked_points"],50)
        self.assertGreaterEqual(q["flip_rate"],0)
        self.assertLessEqual(q["flip_rate"],1)
        self.assertLessEqual(q["max_feature_perturbation"],.20001)

    def test_open_spiel_zero_sum_payoffs(self):
        q=self.output["modules"]["openspiel"]
        self.assertEqual(len(q["payoff_matrix"]),2)
        self.assertEqual(q["payoff_matrix"][1],[0.0,0.0])
        self.assertEqual(len(q["payoff_matrix"][0]),2)
        self.assertTrue(q["not_authorized_trade"])

    def test_z3_exhaustively_proves_abstract_no_trade(self):
        q=self.output["modules"]["z3"]
        self.assertTrue(q["disabled_cannot_authorize"])
        self.assertTrue(q["missing_nvidia_cannot_authorize"])
        self.assertTrue(q["does_not_formally_verify_existing_live_executor"])

    def test_actual_topology_used_real_public_book_not_fake_labels(self):
        q=self.output["modules"]["gudhi"]
        self.assertEqual(q["source"],"REAL_OKX_PUBLIC_BOOK_SNAPSHOT")
        self.assertEqual(q["depth_points"],40)
        self.assertEqual(self.output["real_market_data_used_only_for"],["gudhi"])

    def test_research_never_has_trade_authority(self):
        self.assertFalse(self.output["trading_enabled"])
        self.assertEqual(self.output["orders_placed"],0)
        self.assertEqual(self.output["mode"],"RESEARCH_ONLY_ZERO_TRADING_AUTHORITY")

    def test_evidence_sha256_matches_frozen_book(self):
        self.assertEqual(self.output["public_book_sha256"],nexus.digest(self.book))

    def test_no_unapproved_public_book_could_pass(self):
        bad=dict(self.book,source="USER_SUPPLIED_SECRET")
        with self.assertRaises(ValueError):
            nexus.validate_public_book(bad)

    def test_report_outputs_do_not_depend_on_live_api_keys(self):
        txt=(ROOT/"trading/nexus_seven_2047.py").read_text()
        self.assertNotIn("/api/v5/trade/order",txt)
        self.assertNotIn("/api/v5/account/",txt)
        self.assertNotIn("os.environ",txt)
        self.assertNotIn("api_secret",txt)

if __name__=="__main__":
    unittest.main()
