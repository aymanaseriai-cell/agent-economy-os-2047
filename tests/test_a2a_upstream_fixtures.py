"""Pinned upstream A2A fixtures; no network, signatures, payments or agent execution."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation"))
from a2a_card_audit import audit, public_grpc_address

UPSTREAM_DIR = ROOT / "third_party" / "a2a"

class PinnedA2ARegressionTest(unittest.TestCase):
    def test_protocol_definition_is_pinned_and_contains_agent_card(self):
        p = (UPSTREAM_DIR / "specification" / "a2a.proto").read_text(encoding="utf-8")
        for snippet in ("package lf.a2a.v1;", "message AgentCard {", "message AgentInterface {", "string protocol_binding = 2", "repeated AgentInterface supported_interfaces = 3", "service A2AService {"):
            self.assertIn(snippet, p)

    def test_legacy_official_air_ticketing_fixture_is_flagged_not_approved(self):
        card = json.loads((UPSTREAM_DIR / "fixtures" / "air_ticketing_agent.json").read_text(encoding="utf-8"))
        result = audit(card)
        self.assertEqual(result["status"], "preflight_failed")
        self.assertFalse(result["identity_verified"])
        self.assertIn("required_interfaces", [f["code"] for f in result["failures"]])
        self.assertIn("legacy_card_shape_unverified", [w["code"] for w in result["warnings"]])

    def test_legacy_official_currency_fixture_is_flagged_not_approved(self):
        card = json.loads((UPSTREAM_DIR / "fixtures" / "currency_agent.json").read_text(encoding="utf-8"))
        result = audit(card)
        self.assertEqual(result["status"], "preflight_failed")
        self.assertIn("required_interfaces", [f["code"] for f in result["failures"]])
        self.assertIn("required_mime_modes", [f["code"] for f in result["failures"]])

    def test_grpc_hostname_port_supports_official_agent_interface(self):
        card = {
            "name": "Audit Agent",
            "description": "Checks evidence",
            "version": "1.0.0",
            "supportedInterfaces": [
                {"protocolBinding": "GRPC", "protocolVersion": "1.0", "url": "grpc.example.org:443"}
            ],
            "capabilities": {"streaming": False},
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["application/json"],
            "skills": [{"id": "verify", "name": "Verify", "description": "Check inputs", "tags": ["evidence"]}],
        }
        result = audit(card)
        self.assertEqual(result["status"], "preflight_passed", result)

    def test_grpc_local_and_malformed_addresses_fail_closed(self):
        for target in ("localhost:50051", "127.0.0.1:50051", "10.0.0.1:80",
                       "grpc.example.org:0", "grpc.example.org:65536", "http://grpc.example.org",
                       "grpc.example.org:443/path", "grpc.example.org:443@evil", "grpc.example.org:abc"):
            with self.subTest(target=target):
                self.assertFalse(public_grpc_address(target))

    def test_copied_fixtures_are_not_hosted_service_configuration(self):
        for name in ("air_ticketing_agent.json", "currency_agent.json"):
            card = json.loads((UPSTREAM_DIR / "fixtures" / name).read_text(encoding="utf-8"))
            self.assertTrue(card.get("url", "").startswith("http://localhost"))

if __name__ == "__main__":
    unittest.main()
