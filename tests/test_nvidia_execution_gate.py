import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from trading.nvidia_agent_council import AGENTS
from trading.nvidia_execution_gate import (
    GateRejected, public_snapshot, require_nvidia_veto_pass,
)
from trading.okx_live_executor import ExecutionBlocked, execute


def fixture():
    now = datetime.now(timezone.utc)
    agents = [
        {"agent": key, "signal": "ABSTAIN", "veto": False,
         "evidence": {"observed": "public deterministic measurements"}}
        for key in ("01_liquidity_sentinel", "02_auction_cartographer",
                    "03_tape_detective", "04_derivatives_intelligence",
                    "05_structure_navigator", "06_risk_marshal")
    ]
    agents[-1]["evidence"].update({
        "indicative_stop_not_an_order": 98,
        "indicative_target_not_an_order": 104,
    })
    signal = {
        "symbol": "BTC-USDT-SWAP", "signal": "LONG", "quote_price": 100,
        "advanced_system_count": 7, "advanced_confirmations": 2,
        "advanced_veto_reasons": [], "derivatives_data_warnings": [],
        "execution": "DISABLED", "order_count": 0,
        "last_complete_15m_candle_ms": int(now.timestamp() * 1000) - 16 * 60 * 1000,
        "ordinal_buy_points": 5, "ordinal_sell_points": 0,
        "agents": agents,
    }
    report = {
        "utc_timestamp": now.isoformat(),
        "mode": "SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY",
        "core_specialist_agents": 6, "advanced_quant_systems": 7,
        "results": [signal], "errors": [],
    }
    return report, signal


def council_factory(direction="BUY", critic="BUY", errors=None, opposite=False):
    roles = list(AGENTS.keys())
    directions = [direction, direction, direction, "WAIT", "WAIT", critic]
    if opposite:
        directions[1] = "SELL"
    votes = [
        {"agent": role, "direction": dr, "confidence": 0.85,
         "evidence": ["Evidence"], "risks": []}
        for role, dr in zip(roles, directions)
    ]
    def council(snapshot, api_key=None, model=None):
        assert snapshot["symbol"] == "BTC-USDT-SWAP"
        assert "private_balance" not in snapshot
        return {"mode": "ADVISORY_ONLY", "execution_authorized": False,
                "agents_expected": 6, "agents_responded": 6,
                "errors": [] if errors is None else errors,
                "advisory": direction, "model": "test-nvidia-model",
                "votes": votes}
    return council


class TestNvidiaExecutionGate(unittest.TestCase):
    def test_complete_consensus_passes_as_veto_only(self):
        report, signal = fixture()
        answer = require_nvidia_veto_pass(report, signal, "test",
                                          council_fn=council_factory())
        self.assertEqual(answer["direction"], "BUY")
        self.assertNotIn("execution_authorized", answer)

    def test_missing_key_blocks(self):
        report, signal = fixture()
        with self.assertRaises(GateRejected):
            require_nvidia_veto_pass(report, signal, None,
                                     council_fn=council_factory())

    def test_opposing_vote_blocks(self):
        report, signal = fixture()
        with self.assertRaises(GateRejected):
            require_nvidia_veto_pass(report, signal, "test",
                                     council_fn=council_factory(opposite=True))

    def test_critic_veto_blocks(self):
        report, signal = fixture()
        with self.assertRaises(GateRejected):
            require_nvidia_veto_pass(report, signal, "test",
                                     council_fn=council_factory(critic="WAIT"))

    def test_any_agent_error_blocks(self):
        report, signal = fixture()
        with self.assertRaises(GateRejected):
            require_nvidia_veto_pass(report, signal, "test",
                     council_fn=council_factory(errors=[{"agent": "risk_critic"}]))

    def test_stale_report_blocks_before_ai(self):
        report, signal = fixture()
        report["utc_timestamp"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with self.assertRaises(GateRejected):
            require_nvidia_veto_pass(report, signal, "test",
                                     council_fn=lambda *a, **k: self.fail("No model calls"))

    def test_public_snapshot_omits_private_fields(self):
        report, signal = fixture()
        report["api_secret"] = "NEVER_COPY"
        signal["private_balance"] = "NEVER_COPY"
        snapshot = public_snapshot(report, signal)
        self.assertNotIn("NEVER_COPY", repr(snapshot))

    def test_nvidia_network_failure_blocks(self):
        report, signal = fixture()
        def offline(*args, **kwargs):
            raise TimeoutError()
        with self.assertRaises(GateRejected):
            require_nvidia_veto_pass(report, signal, "test", council_fn=offline)

    def test_live_will_not_call_exchange_without_nvidia_key(self):
        report, signal = fixture()
        env = {
            "OKX_EXECUTION_ARM": "I_ACCEPT_REAL_MONEY_LOSS",
            "OKX_ENABLE_REAL_TRADING": "YES",
            "OKX_API_KEY": "test", "OKX_SECRET_KEY": "test",
            "OKX_PASSPHRASE": "test", "OKX_CAPITAL_MODE": "guarded",
        }
        class Never:
            def request(self, *args, **kwargs):
                raise AssertionError("Exchange request preceded NVIDIA veto")
        with self.assertRaisesRegex(ExecutionBlocked, "AI pre-trade veto"):
            execute(report, Never(), "live", env)

    def test_dry_run_will_not_request_nvidia_or_exchange(self):
        report, signal = fixture()
        class Never:
            def request(self, *args, **kwargs):
                raise AssertionError("Unexpected OKX call")
        with patch("trading.okx_live_executor.require_nvidia_veto_pass",
                   side_effect=AssertionError("Unexpected NVIDIA call")):
            self.assertEqual(execute(report, Never(), "dry_run", {}), "DRY_RUN_SIGNAL_ONLY")


if __name__ == "__main__":
    unittest.main()
