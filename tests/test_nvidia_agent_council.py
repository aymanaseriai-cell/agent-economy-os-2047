import json
import unittest
from unittest.mock import patch

from trading.nvidia_agent_council import (
    AGENTS, CouncilError, _extract_json, run_council,
)


class NvidiaCouncilTests(unittest.TestCase):
    def test_extracts_valid_vote(self):
        result = _extract_json('{"direction":"BUY","confidence":0.8,"evidence":["x"],"risks":[]}') 
        self.assertEqual(result["direction"], "BUY")
        self.assertEqual(result["confidence"], 0.8)

    def test_rejects_invalid_direction(self):
        with self.assertRaises(CouncilError):
            _extract_json('{"direction":"MOON","confidence":0.9,"evidence":[],"risks":[]}')

    def test_rejects_confidence_out_of_range(self):
        with self.assertRaises(CouncilError):
            _extract_json('{"direction":"BUY","confidence":1.5,"evidence":[],"risks":[]}')

    @patch("trading.nvidia_agent_council.call_agent")
    def test_council_requires_six_responses_and_four_aligned_votes(self, mocked):
        mocked.side_effect = [
            {"agent": n, "direction": "BUY", "confidence": 0.8, "evidence": [], "risks": []}
            for n in list(AGENTS)[:4]
        ] + [CouncilError("simulated failure"), CouncilError("simulated failure")]
        # Convert raised errors to the same fail-closed path used by the runner.
        def side_effect(name, *args, **kwargs):
            if name in list(AGENTS)[4:]:
                raise CouncilError("simulated failure")
            return {"agent": name, "direction": "BUY", "confidence": 0.8, "evidence": [], "risks": []}
        mocked.side_effect = side_effect
        result = run_council({"symbol": "TEST"}, api_key="test")
        self.assertEqual(result["advisory"], "WAIT")
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["agents_responded"], 4)

    @patch("trading.nvidia_agent_council.call_agent")
    def test_six_aligned_votes_are_still_advisory_only(self, mocked):
        mocked.side_effect = lambda name, *a, **k: {
            "agent": name, "direction": "SELL", "confidence": 0.8,
            "evidence": [], "risks": []
        }
        result = run_council({"symbol": "TEST"}, api_key="test")
        self.assertEqual(result["advisory"], "SELL")
        self.assertFalse(result["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
