"""Offline positive/negative evidence demo for the non-binding USD 49 starter."""
import unittest

from automation.starter_49_demo import run_demo


class Starter49DemoTests(unittest.TestCase):
    def test_sample_pass_tampered_bytes_and_swapped_policy_fail(self):
        result = run_demo()
        self.assertTrue(result["ok"], result)
        self.assertIs(result["baseline"]["passed"], True)
        self.assertEqual(result["baseline"]["checked"], 3)
        self.assertIs(result["tampered_artifact"]["rejected"], True)
        self.assertIs(result["swapped_policy"]["rejected"], True)
        self.assertIn("POLICY_PIN_MISMATCH", result["swapped_policy"]["reason"])

    def test_no_unjustified_commercial_or_provenance_claim(self):
        result = run_demo()
        self.assertEqual(result["policy_digest_source"], "same_checkout_local_smoke_only")
        self.assertEqual(result["network_calls"], 0)
        self.assertEqual(result["payment_calls"], 0)
        for label in ("customer_identity_verified", "buyer_authority_verified",
                      "independent_provenance_verified", "external_freshness_verified",
                      "paid_delivery_verified", "commercial_revenue_verified"):
            self.assertIs(result[label], False)


if __name__ == "__main__":
    unittest.main()
