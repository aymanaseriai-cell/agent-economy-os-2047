import unittest
from unittest.mock import patch
from trading.nvidia_agent_council import AGENTS, CouncilError, _extract_json, run_council

class NvidiaCouncilTests(unittest.TestCase):
    def test_valid_json(self):
        self.assertEqual(_extract_json('{"direction":"BUY","confidence":0.8,"evidence":[],"risks":[]}')["direction"], "BUY")
    def test_rejects_missing_text_content(self):
        with self.assertRaises(CouncilError):
            _extract_json(None)
    def test_rejects_incomplete_model_response(self):
        with self.assertRaises(CouncilError):
            _extract_json('{"foo":"bar"}')
    def test_rejects_invalid_direction(self):
        with self.assertRaises(CouncilError):
            _extract_json('{"direction":"MOON","confidence":0.8,"evidence":[],"risks":[]}')
    def test_rejects_confidence_out_of_range(self):
        with self.assertRaises(CouncilError):
            _extract_json('{"direction":"BUY","confidence":2,"evidence":[],"risks":[]}')
    @patch("trading.nvidia_agent_council.select_model", return_value="test-model")
    @patch("trading.nvidia_agent_council.call_agent")
    def test_missing_agent_fails_closed(self, call, select):
        def answer(name, *args):
            if name == "news": raise CouncilError("offline")
            return {"agent":name,"direction":"BUY","confidence":0.9,"evidence":[],"risks":[]}
        call.side_effect = answer
        result = run_council({"symbol":"TEST"}, api_key="test")
        self.assertEqual(result["advisory"], "WAIT")
        self.assertFalse(result["execution_authorized"])
    @patch("trading.nvidia_agent_council.select_model", return_value="test-model")
    @patch("trading.nvidia_agent_council.call_agent")
    def test_direction_is_advisory_only(self, call, select):
        call.side_effect = lambda name,*a: {"agent":name,"direction":"SELL","confidence":0.8,"evidence":[],"risks":[]}
        result = run_council({"symbol":"TEST"}, api_key="test")
        self.assertEqual(result["advisory"], "SELL")
        self.assertFalse(result["execution_authorized"])


    @patch("trading.nvidia_agent_council.list_models", return_value=["nvidia/nemotron-3-super-120b-a12b", "nvidia/llama-3.1-nemotron-safety-guard-8b-v3", "meta/llama-3.3-70b-instruct"])
    def test_filters_safety_guard_from_chat_fallbacks(self, models):
        from trading.nvidia_agent_council import _fallback_models
        self.assertNotIn("nvidia/llama-3.1-nemotron-safety-guard-8b-v3", _fallback_models("test","nvidia/nemotron-3-super-120b-a12b"))

    @patch("trading.nvidia_agent_council._fallback_models", return_value=["meta/llama-3.3-70b-instruct"])
    @patch("trading.nvidia_agent_council.select_model", return_value="unavailable-model")
    @patch("trading.nvidia_agent_council.call_agent")
    def test_fallback_on_missing_inference_route(self, call, select, fallback):
        def answer(name, role, snapshot, key, model):
            if model == "unavailable-model":
                raise CouncilError("NVIDIA inference HTTP 404")
            return {"agent":name,"direction":"WAIT","confidence":0.9,"evidence":[],"risks":[]}
        call.side_effect=answer
        result=run_council({"symbol":"TEST"},api_key="test")
        self.assertEqual(result["model"],"meta/llama-3.3-70b-instruct")
        self.assertEqual(result["agents_responded"],len(AGENTS))
        self.assertEqual(result["advisory"],"WAIT")
        self.assertFalse(result["execution_authorized"])

    @patch("trading.nvidia_agent_council._fallback_models", return_value=["second-model"])
    @patch("trading.nvidia_agent_council.select_model", return_value="first-model")
    @patch("trading.nvidia_agent_council.call_agent", side_effect=CouncilError("NVIDIA inference HTTP 404"))
    def test_no_inference_route_is_fail_closed(self, call, select, fallback):
        result=run_council({"symbol":"TEST"},api_key="test")
        self.assertEqual(result["agents_responded"],0)
        self.assertEqual(result["advisory"],"WAIT")
        self.assertFalse(result["execution_authorized"])

if __name__ == "__main__": unittest.main()
