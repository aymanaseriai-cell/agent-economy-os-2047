"""Regression tests: NVIDIA opinion must not determine whether live quant trades execute."""
import contextlib
import io
import os
import sys
import unittest
from unittest.mock import patch

from tests.test_nvidia_execution_gate import fixture, council_factory
from trading.nvidia_execution_gate import GateConsensusVeto, require_nvidia_veto_pass
from trading.okx_live_executor import ExecutionBlocked, execute, main


def live_fixture_env():
    return {
        "OKX_EXECUTION_MODE": "live",
        "OKX_ENABLE_REAL_TRADING": "YES",
        "OKX_EXECUTION_ARM": "I_ACCEPT_REAL_MONEY_LOSS",
        "OKX_CAPITAL_MODE": "guarded",
        "OKX_API_KEY": "fake-key-test-only",
        "OKX_SECRET_KEY": "fake-secret-test-only",
        "OKX_PASSPHRASE": "fake-passphrase-test-only",
    }


class NvidiaDetachedFromExecutionTests(unittest.TestCase):
    def test_legacy_research_veto_still_reports_critic_disagreement(self):
        report, signal = fixture()
        with self.assertRaises(GateConsensusVeto):
            require_nvidia_veto_pass(
                report, signal, "fake-key-test-only",
                council_fn=council_factory(critic="WAIT"),
            )

    def test_legacy_research_veto_reports_opposing_vote(self):
        report, signal = fixture()
        with self.assertRaises(GateConsensusVeto):
            require_nvidia_veto_pass(
                report, signal, "fake-key-test-only",
                council_fn=council_factory(opposite=True),
            )

    def test_live_executor_has_no_nvidia_dependency(self):
        report, signal = fixture()
        with patch("trading.nvidia_agent_council.run_council",
                   side_effect=RuntimeError("NVIDIA unavailable")) as nvidia:
            with patch("trading.okx_live_executor.market_preflight",
                       side_effect=ExecutionBlocked("Exchange spread veto")) as exchange:
                with self.assertRaisesRegex(ExecutionBlocked, "Exchange spread veto"):
                    execute(report, object(), "live", live_fixture_env())
        nvidia.assert_not_called()
        exchange.assert_called_once()

    def test_live_executor_keeps_quant_signal_requirement(self):
        report, signal = fixture()
        signal["advanced_veto_reasons"] = ["high_jump_risk"]
        with patch("trading.okx_live_executor.market_preflight",
                   side_effect=AssertionError("No qualifying quant signal")):
            self.assertEqual(execute(report, object(), "live", live_fixture_env()),
                             "NO_CONSENSUS")

    def test_cli_exchange_failure_remains_blocked(self):
        out, errs = io.StringIO(), io.StringIO()
        with (patch.dict(os.environ, live_fixture_env()),
              patch.object(sys, "argv", ["okx_live_executor", "--mode", "live"]),
              patch("trading.okx_live_executor.read_report", return_value=fixture()[0]),
              patch("trading.okx_live_executor.execute",
                    side_effect=ExecutionBlocked("Exchange spread veto")),
              contextlib.redirect_stdout(out), contextlib.redirect_stderr(errs)):
            code = main()
        self.assertEqual(code, 2)
        self.assertNotIn("AI_VETO", out.getvalue())
        self.assertIn("Exchange spread veto", errs.getvalue())


if __name__ == "__main__":
    unittest.main()
