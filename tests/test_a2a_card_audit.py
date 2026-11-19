import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation"))
from a2a_card_audit import audit, public_https

def valid():
    return {
        "name": "Evidence Agent",
        "description": "Deterministic evidence checks",
        "version": "1.0.0",
        "supportedInterfaces": [{"protocolBinding": "JSONRPC", "protocolVersion": "1.0", "url": "https://agent.example.org/a2a"}],
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text/plain"], "defaultOutputModes": ["application/json"],
        "skills": [{"id": "check", "name": "Check", "description": "Check artifacts", "tags": ["verification"]}],
    }

class AuditTest(unittest.TestCase):
    def test_valid_card_is_not_identity_proof(self):
        result = audit(valid())
        self.assertEqual(result["status"], "preflight_passed")
        self.assertFalse(result["identity_verified"])
        self.assertFalse(result["signature_verified"])
    def test_missing_required_field(self):
        card = valid(); del card["supportedInterfaces"]
        self.assertEqual(audit(card)["status"], "preflight_failed")
    def test_duplicate_skill_id(self):
        card = valid(); card["skills"].append(dict(card["skills"][0]))
        self.assertIn("duplicate_skill_id", [e["code"] for e in audit(card)["failures"]])
    def test_unsafe_endpoints(self):
        for url in ["http://example.org", "https://127.0.0.1/", "https://localhost/", "https://user:pass@example.org/", "https://192.168.1.1", "https://x.internal", "https://example.org:999"]:
            with self.subTest(url=url):
                self.assertFalse(public_https(url))
    def test_signature_not_verified(self):
        card = valid(); card["signatures"] = [{"jws": "untrusted"}]
        result = audit(card)
        self.assertFalse(result["signature_verified"])
        self.assertIn("signatures_not_verified", [e["code"] for e in result["warnings"]])
    def test_duplicate_json_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            card = Path(td) / "card.json"
            card.write_text('{"name":"a","name":"b"}', encoding="utf-8")
            script = Path(__file__).resolve().parents[1] / "automation" / "a2a_card_audit.py"
            result = subprocess.run([sys.executable, str(script), str(card)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["status"], "preflight_failed")
    def test_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as td:
            card = Path(td) / "card.json"; card.write_text(json.dumps(valid()), encoding="utf-8")
            report = Path(td) / "report.json"
            script = Path(__file__).resolve().parents[1] / "automation" / "a2a_card_audit.py"
            p = subprocess.run([sys.executable, str(script), str(card), "--json-out", str(report)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0)
            self.assertEqual(json.loads(report.read_text())["status"], "preflight_passed")

if __name__ == "__main__":
    unittest.main()
