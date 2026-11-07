import unittest
from unittest.mock import patch
from trading.nvidia_agent_council import AGENTS, CouncilError, _extract_json, run_council

class NvidiaCouncilTests(unittest.TestCase):
    def test_valid_json(self):
        self.assertEqual(_extract_json('{"direction":"BUY","confidence":0.8,"evidence":[],"risks":[]}')["direction"], "BUY")
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

if __name__ == "__main__": unittest.main()
