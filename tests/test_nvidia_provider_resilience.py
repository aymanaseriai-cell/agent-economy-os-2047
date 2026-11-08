import unittest
from unittest.mock import patch
from trading.nvidia_agent_council import (
    AGENTS, CouncilError, _extract_json, call_agent_with_one_safe_retry,
    run_council,
)
from trading.nvidia_execution_gate import safe_nvidia_error_summary


def good(name, role, snapshot, api_key, model):
    return {"agent":name,"direction":"WAIT","confidence":0.9,
            "evidence":["synthetic test only"],"risks":[]}


class ProviderResilienceTests(unittest.TestCase):
    @patch("trading.nvidia_agent_council.time.sleep")
    @patch("trading.nvidia_agent_council.call_agent")
    def test_one_429_retry_then_valid_decision(self, agent, sleep):
        agent.side_effect=[CouncilError("NVIDIA inference HTTP 429"),good("trend",None,None,None,None)]
        result=call_agent_with_one_safe_retry("trend","test",{},"fake","test")
        self.assertEqual(result["direction"],"WAIT")
        self.assertEqual(agent.call_count,2)
        sleep.assert_called_once_with(0.6)

    @patch("trading.nvidia_agent_council.time.sleep")
    @patch("trading.nvidia_agent_council.call_agent",side_effect=CouncilError("NVIDIA inference HTTP 401"))
    def test_never_retry_auth_failure(self, agent, sleep):
        with self.assertRaises(CouncilError):
            call_agent_with_one_safe_retry("trend","test",{},"fake","test")
        self.assertEqual(agent.call_count,1)
        sleep.assert_not_called()

    @patch("trading.nvidia_agent_council.time.sleep")
    @patch("trading.nvidia_agent_council.call_agent",side_effect=CouncilError("NVIDIA inference HTTP 429"))
    def test_rate_limit_retry_is_bounded(self, agent, sleep):
        with self.assertRaises(CouncilError):
            call_agent_with_one_safe_retry("trend","test",{},"fake","test")
        self.assertEqual(agent.call_count,2)
        sleep.assert_called_once()

    @patch("trading.nvidia_agent_council.select_model",return_value="test-model")
    @patch("trading.nvidia_agent_council.time.sleep")
    @patch("trading.nvidia_agent_council.call_agent")
    def test_transient_first_call_can_recover_but_never_authorizes_trade(self, agent, sleep, model):
        values=[CouncilError("NVIDIA inference HTTP 503")]
        def side_effect(name,role,snapshot,key,selected):
            if values:
                raise values.pop()
            return good(name,role,snapshot,key,selected)
        agent.side_effect=side_effect
        res=run_council({"symbol":"TEST"},api_key="test")
        self.assertEqual(res["agents_responded"],6)
        self.assertEqual(res["errors"],[])
        self.assertEqual(res["advisory"],"WAIT")
        self.assertIs(res["execution_authorized"],False)
        self.assertEqual(agent.call_count,7)

    @patch("trading.nvidia_agent_council.select_model",return_value="test-model")
    @patch("trading.nvidia_agent_council.time.sleep")
    @patch("trading.nvidia_agent_council.call_agent",side_effect=CouncilError("NVIDIA inference HTTP 429"))
    def test_permanent_429_still_fails_closed_and_reports_safe_error_code(self, agent,sleep,model):
        response=run_council({"symbol":"TEST"},api_key="test")
        self.assertEqual(response["agents_responded"],0)
        self.assertEqual(response["advisory"],"WAIT")
        self.assertIs(response["execution_authorized"],False)
        summary=safe_nvidia_error_summary(response)
        self.assertIn("HTTP_429",summary)
        self.assertIn("NO_USABLE_MODEL",summary)
        self.assertEqual(agent.call_count,2)

    def test_safe_errors_never_echo_sensitive_model_output(self):
        response={
            "agents_responded":0,
            "errors":[{"agent":"trend","error":"No usable inference model responded"}],
            "model_attempts":[{"model":"private-provider-name",
                               "error":"NVIDIA inference HTTP 503 secret-do-not-print"}],
        }
        summary=safe_nvidia_error_summary(response)
        self.assertIn("HTTP_503",summary)
        self.assertNotIn("secret-do-not-print",summary)
        self.assertNotIn("private-provider-name",summary)

    def test_invalid_numeric_confidence_is_controlled_failure(self):
        with self.assertRaises(CouncilError):
            _extract_json('{"direction":"BUY","confidence":"not-a-number","evidence":[],"risks":[]}')


if __name__=="__main__":
    unittest.main()
