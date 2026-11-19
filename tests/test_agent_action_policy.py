import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation"))
from agent_action_policy import (
    POLICY_SCHEMA, REQUEST_SCHEMA, PolicyError, evaluate, read_strict_json, validate_policy
)

def policy():
    return {"schema": POLICY_SCHEMA, "rules": [{
        "id": "read_public_evidence", "effect": "allow",
        "principals": ["audit-agent"], "actions": ["evidence.inspect", "repo.inspect"],
        "resources": ["service:work-covenant", "github:aymanaseriai-cell/agent-economy-os-2047"],
        "environments": ["staging", "production"], "expires_at": "2027-12-31T23:59:59Z"
    }]}

def request():
    return {"schema": REQUEST_SCHEMA, "principal": "audit-agent",
            "action": "evidence.inspect", "resource": "service:work-covenant",
            "environment": "staging"}

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)

class PolicyTest(unittest.TestCase):
    def test_allow_does_not_assert_authentication_or_execution(self):
        result = evaluate(policy(), request(), clock=NOW)
        self.assertEqual(result["decision"], "allow")
        self.assertFalse(result["principal_authenticated"])
        self.assertFalse(result["credential_verified"])
        self.assertFalse(result["action_executed"])
        self.assertEqual(result["matching_rule_ids"], ["read_public_evidence"])

    def test_default_deny(self):
        self.assertEqual(evaluate({"schema": POLICY_SCHEMA, "rules": []}, request(), clock=NOW)["decision"], "deny")

    def test_wrong_principal_resource_environment_or_action_denied(self):
        for key, bad in (("principal", "attacker"), ("resource", "service:unknown"),
                         ("environment", "local"), ("action", "health.inspect")):
            with self.subTest(field=key):
                r = request(); r[key] = bad
                self.assertEqual(evaluate(policy(), r, clock=NOW)["decision"], "deny")

    def test_hard_blocked_operations(self):
        for op in ("payment.settle", "x402.settle", "db.write", "production.deploy",
                   "wallet.transfer", "trade.place_order", "secrets.read", "email.send"):
            r = request(); r["action"] = op
            with self.subTest(action=op):
                result = evaluate(policy(), r, clock=NOW)
                self.assertEqual(result["decision"], "deny")
                self.assertEqual(result["reason"], "hard_blocked_action")

    def test_unknown_action_denied(self):
        r = request(); r["action"] = "unknown.action"
        self.assertEqual(evaluate(policy(), r, clock=NOW)["reason"], "unsupported_action")

    def test_expired_rule_denied(self):
        later = datetime(2028, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(evaluate(policy(), request(), clock=later)["decision"], "deny")

    def test_explicit_deny_overrides_allow(self):
        p = policy()
        p["rules"].append(dict(p["rules"][0], id="block_inspection", effect="deny"))
        result = evaluate(p, request(), clock=NOW)
        self.assertEqual(result["decision"], "deny")
        self.assertEqual(result["reason"], "explicit_deny")

    def test_wildcard_and_payment_policy_rules_invalid(self):
        for name, value in (("principals", ["*"]), ("resources", ["service:*"]),
                            ("actions", ["payment.settle"])):
            p = policy(); p["rules"][0][name] = value
            with self.subTest(name=name), self.assertRaises(PolicyError):
                validate_policy(p)

    def test_unknown_fields_and_claimed_approval_invalid(self):
        p = policy(); p["rules"][0]["skip"] = True
        with self.assertRaises(PolicyError):
            validate_policy(p)
        r = request(); r["approved"] = True
        with self.assertRaises(PolicyError):
            evaluate(policy(), r, clock=NOW)

    def test_duplicate_rule_ids_rejected(self):
        p = policy(); p["rules"].append(dict(p["rules"][0]))
        with self.assertRaises(PolicyError):
            validate_policy(p)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaises(PolicyError):
                read_strict_json(path)

    def test_nonfinite_json_numbers_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            for body in ('{"n":NaN}', '{"n":Infinity}', '{"n":1e999}'):
                path.write_text(body, encoding="utf-8")
                with self.subTest(body=body), self.assertRaises(PolicyError):
                    read_strict_json(path)

    def test_resource_path_traversal_rejected(self):
        r = request(); r["resource"] = "github:owner/../repo"
        with self.assertRaises(PolicyError):
            evaluate(policy(), r, clock=NOW)

    def test_deterministic_policy_digest(self):
        first = evaluate(policy(), request(), clock=NOW)
        second = evaluate(policy(), request(), clock=NOW)
        self.assertEqual(first["policy_sha256"], second["policy_sha256"])

    def test_example_policy_is_valid(self):
        path = ROOT / "policies" / "agent_action_policy.example.json"
        self.assertEqual(validate_policy(read_strict_json(path))["schema"], POLICY_SCHEMA)

    def test_cli_hard_blocks_wallet_action(self):
        with tempfile.TemporaryDirectory() as td:
            pp = Path(td) / "policy.json"
            rp = Path(td) / "request.json"
            pp.write_text(json.dumps(policy()), encoding="utf-8")
            r = request(); r["action"] = "wallet.transfer"
            rp.write_text(json.dumps(r), encoding="utf-8")
            process = subprocess.run(
                [sys.executable, str(ROOT / "automation" / "agent_action_policy.py"), str(pp), str(rp)],
                capture_output=True, text=True
            )
            self.assertEqual(process.returncode, 1)
            self.assertEqual(json.loads(process.stdout)["decision"], "deny")

if __name__ == "__main__":
    unittest.main()
