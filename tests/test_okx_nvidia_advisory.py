"""No secret, exchange order, or inference opinion may affect live decisions."""
import unittest
from unittest.mock import patch

from tests.test_nvidia_execution_gate import fixture, council_factory
from trading.okx_nvidia_advisory import advisory_only


class DetachedAdvisoryTests(unittest.TestCase):
    def test_nvidia_wait_is_recorded_but_never_authorizes_execution(self):
        report, _ = fixture()
        opinion = advisory_only(report, "test-only", council_fn=council_factory(critic="WAIT"))
        self.assertEqual(opinion["status"], "COMPLETE")
        self.assertFalse(opinion["execution_authorized"])
        self.assertFalse(opinion["used_by_order_executor"])
        self.assertIn(opinion["advisory"], ("BUY", "SELL", "WAIT"))
        self.assertEqual(opinion["roles_responded"], 6)

    def test_opposing_vote_is_research_not_execution_veto(self):
        report, _ = fixture()
        opinion = advisory_only(report, "test-only", council_fn=council_factory(opposite=True))
        self.assertEqual(opinion["role_counts"]["SELL"], 1)
        self.assertFalse(opinion["used_by_order_executor"])

    def test_missing_key_is_never_fatal(self):
        report, _ = fixture()
        with patch("trading.nvidia_agent_council.run_council",
                   side_effect=AssertionError("Model must not run")):
            opinion = advisory_only(report, None)
        self.assertEqual(opinion["status"], "NVIDIA_NOT_CONFIGURED")

    def test_inference_failure_never_becomes_execution_failure(self):
        report, _ = fixture()
        def unavailable(*args, **kwargs):
            raise TimeoutError("Sensitive provider output")
        opinion = advisory_only(report, "test-only", council_fn=unavailable)
        self.assertEqual(opinion["status"], "ADVISORY_UNAVAILABLE")
        self.assertNotIn("Sensitive provider output", repr(opinion))

    def test_quant_veto_blocks_advisory_inference(self):
        report, signal = fixture()
        signal["advanced_veto_reasons"] = ["volatility"]
        def no_model(*args, **kwargs):
            self.fail("Should not contact NVIDIA when no quant candidate exists")
        opinion = advisory_only(report, "test-only", council_fn=no_model)
        self.assertEqual(opinion["status"], "NO_SIGNAL")

    def test_private_fields_never_enter_advisory_snapshot(self):
        report, signal = fixture()
        report["account_key"] = "PRIVATE_DO_NOT_USE"
        signal["account_balance"] = "PRIVATE_DO_NOT_USE"
        def verify(snapshot, **kwargs):
            self.assertNotIn("PRIVATE_DO_NOT_USE", repr(snapshot))
            return council_factory()(snapshot, **kwargs)
        opinion = advisory_only(report, "test-only", council_fn=verify)
        self.assertNotIn("PRIVATE_DO_NOT_USE", repr(opinion))


if __name__ == "__main__":
    unittest.main()
