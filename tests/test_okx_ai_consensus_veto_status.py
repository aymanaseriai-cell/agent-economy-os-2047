import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests.test_nvidia_execution_gate import fixture, council_factory
from trading.nvidia_execution_gate import (
    GateRejected, GateConsensusVeto, require_nvidia_veto_pass,
)
from trading.okx_live_executor import (
    ExecutionBlocked, ExecutionNoTrade, execute, main,
)
from trading.okx_five_second_worker import loop


def live_fixture_env():
    return {
        "OKX_EXECUTION_MODE": "live",
        "OKX_ENABLE_REAL_TRADING": "YES",
        "OKX_EXECUTION_ARM": "I_ACCEPT_REAL_MONEY_LOSS",
        "OKX_CAPITAL_MODE": "guarded",
        "NVIDIA_API_KEY": "fake-key-test-only",
        "OKX_API_KEY": "fake-key-test-only",
        "OKX_SECRET_KEY": "fake-secret-test-only",
        "OKX_PASSPHRASE": "fake-passphrase-test-only",
    }


class NoExchangeClient:
    def request(self, *args, **kwargs):
        raise AssertionError("An explicit AI veto must not query OKX")


class ExplicitNvidiaVetoTests(unittest.TestCase):
    def test_valid_critic_veto_is_consensus_veto(self):
        report, signal = fixture()
        with self.assertRaises(GateConsensusVeto):
            require_nvidia_veto_pass(
                report, signal, "fake-key-test-only",
                council_fn=council_factory(critic="WAIT"),
            )

    def test_valid_opposing_vote_is_consensus_veto(self):
        report, signal = fixture()
        with self.assertRaises(GateConsensusVeto):
            require_nvidia_veto_pass(
                report, signal, "fake-key-test-only",
                council_fn=council_factory(opposite=True),
            )

    def test_missing_key_still_hard_rejected(self):
        report, signal = fixture()
        with self.assertRaises(GateRejected) as err:
            require_nvidia_veto_pass(report, signal, None)
        self.assertNotIsInstance(err.exception, GateConsensusVeto)

    def test_explicit_ai_veto_blocks_all_private_exchange_calls(self):
        report, signal = fixture()
        with patch("trading.okx_live_executor.require_nvidia_veto_pass",
                   side_effect=GateConsensusVeto("NVIDIA consensus or risk critic vetoed this trade")):
            with self.assertRaises(ExecutionNoTrade):
                execute(report, NoExchangeClient(), "live", live_fixture_env())

    def test_invalid_model_data_remains_hard_failure(self):
        report, signal = fixture()
        with patch("trading.okx_live_executor.require_nvidia_veto_pass",
                   side_effect=GateRejected("Unverified NVIDIA council response")):
            with self.assertRaises(ExecutionBlocked) as err:
                execute(report, NoExchangeClient(), "live", live_fixture_env())
        self.assertNotIsInstance(err.exception, ExecutionNoTrade)

    def test_cli_distinguishes_veto_from_failure(self):
        out, errs = io.StringIO(), io.StringIO()
        with (patch.dict(os.environ,live_fixture_env()),
              patch.object(sys,"argv",["okx_live_executor","--mode","live"]),
              patch("trading.okx_live_executor.read_report",return_value=fixture()[0]),
              patch("trading.okx_live_executor.OKX",return_value=NoExchangeClient()),
              patch("trading.okx_live_executor.execute",side_effect=ExecutionNoTrade("explicit veto")),
              contextlib.redirect_stdout(out), contextlib.redirect_stderr(errs)):
            code=main()
        self.assertEqual(code,0)
        self.assertIn("OKX EXECUTION RESULT: AI_VETO_NO_ORDER",out.getvalue())
        self.assertIn("NO ORDER",errs.getvalue())

    def test_worker_stops_without_retry_after_ai_veto(self):
        calls=[]
        def run(args,timeout):
            calls.append(args[2])
            if args[2]=="trading.okx_live_executor":
                return subprocess.CompletedProcess(args,0,"OKX EXECUTION RESULT: AI_VETO_NO_ORDER\n","")
            return subprocess.CompletedProcess(args,0,"","")
        code=loop(max_cycles=8,run=run,clock=lambda:0.0,
                  sleep=lambda _n:self.fail("Risk veto must not retry"))
        self.assertEqual(code,0)
        self.assertEqual(calls,["trading.six_agent_council","trading.okx_live_executor"])


if __name__=="__main__":
    unittest.main()
