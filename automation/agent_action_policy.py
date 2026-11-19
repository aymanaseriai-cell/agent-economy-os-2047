#!/usr/bin/env python3
"""Offline, deny-by-default preflight for Agent Economy OS 2047 agent actions.

This evaluates claimed principals against a trusted local policy; it never
authenticates anyone, executes commands, accesses accounts or transfers money.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
from pathlib import Path

POLICY_SCHEMA = "agent-economy.action-policy.v1"
REQUEST_SCHEMA = "agent-economy.action-request.v1"
MAX_FILE_BYTES = 65536
SAFE_ACTIONS = frozenset({
    "repo.inspect", "agent_card.preflight", "evidence.inspect",
    "work_covenant.compile", "work_covenant.evaluate", "health.inspect"
})
HIGH_RISK = frozenset({
    "db.write", "production.deploy", "payment.settle", "x402.settle",
    "wallet.transfer", "trade.place_order", "secrets.read", "email.send",
    "account.modify", "agent.execute_untrusted", "repository.delete"
})
ENVIRONMENTS = frozenset({"local", "staging", "production"})
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
RULE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
RESOURCE_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}:[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")

class PolicyError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError("duplicate_json_key")
        result[key] = value
    return result

def reject_nonfinite(value):
    raise PolicyError("nonfinite_json_number")

def finite_float(raw):
    number = float(raw)
    if not (-float("inf") < number < float("inf")):
        raise PolicyError("nonfinite_json_number")
    return number

def read_strict_json(path):
    file = Path(path)
    try:
        size = file.stat().st_size
    except OSError as exc:
        raise PolicyError("input_missing_or_too_large") from exc
    if not file.is_file() or size > MAX_FILE_BYTES:
        raise PolicyError("input_missing_or_too_large")
    try:
        return json.loads(file.read_text(encoding="utf-8"),
                          object_pairs_hook=unique_pairs,
                          parse_constant=reject_nonfinite,
                          parse_float=finite_float)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise PolicyError("invalid_json") from exc

def exact_keys(item, required, allowed, code):
    if not isinstance(item, dict) or not required <= item.keys() or not item.keys() <= allowed:
        raise PolicyError(code)

def selector(value, pattern):
    return isinstance(value, str) and len(value) <= 128 and pattern.fullmatch(value) is not None

def valid_resource(value):
    return selector(value, RESOURCE_RE) and ".." not in value and "//" not in value

def expires_at(value):
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value) is None:
        raise PolicyError("invalid_expiry")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise PolicyError("invalid_expiry") from exc

def validate_policy(policy):
    exact_keys(policy, {"schema", "rules"}, {"schema", "rules"}, "invalid_policy_shape")
    if policy["schema"] != POLICY_SCHEMA:
        raise PolicyError("unsupported_policy_schema")
    rules = policy["rules"]
    if not isinstance(rules, list) or len(rules) > 64:
        raise PolicyError("invalid_rule_count")
    seen = set()
    for rule in rules:
        required = {"id", "effect", "principals", "actions", "resources", "environments"}
        exact_keys(rule, required, required | {"expires_at"}, "invalid_rule_shape")
        if not selector(rule["id"], RULE_RE) or rule["id"] in seen:
            raise PolicyError("invalid_or_duplicate_rule_id")
        seen.add(rule["id"])
        if rule["effect"] not in ("allow", "deny"):
            raise PolicyError("invalid_rule_effect")
        validators = (
            ("principals", lambda x: selector(x, NAME_RE)),
            ("actions", lambda x: isinstance(x, str) and x in SAFE_ACTIONS),
            ("resources", valid_resource),
            ("environments", lambda x: isinstance(x, str) and x in ENVIRONMENTS),
        )
        for field, predicate in validators:
            values = rule[field]
            if (not isinstance(values, list) or not (1 <= len(values) <= 32)
                or len(values) != len(set(map(str, values)))
                or not all(predicate(v) for v in values)):
                raise PolicyError("invalid_rule_" + field)
        if "expires_at" in rule:
            expires_at(rule["expires_at"])
    return policy

def validate_request(request):
    keys = {"schema", "principal", "action", "resource", "environment"}
    exact_keys(request, keys, keys, "invalid_request_shape")
    if request["schema"] != REQUEST_SCHEMA:
        raise PolicyError("unsupported_request_schema")
    if not selector(request["principal"], NAME_RE):
        raise PolicyError("invalid_principal")
    if not isinstance(request["action"], str) or len(request["action"]) > 128:
        raise PolicyError("invalid_action")
    if not valid_resource(request["resource"]):
        raise PolicyError("invalid_resource")
    if not isinstance(request["environment"], str) or request["environment"] not in ENVIRONMENTS:
        raise PolicyError("invalid_environment")
    return request

def evaluate(policy, request, *, clock=None):
    validate_policy(policy)
    validate_request(request)
    now = clock if clock is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise PolicyError("invalid_clock")
    digest = hashlib.sha256(json.dumps(
        policy, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")).hexdigest()
    decision, reason = "deny", "no_matching_allow_rule"
    matched = []
    if request["action"] in HIGH_RISK:
        reason = "hard_blocked_action"
    elif request["action"] not in SAFE_ACTIONS:
        reason = "unsupported_action"
    else:
        matching = [
            rule for rule in policy["rules"]
            if request["principal"] in rule["principals"]
            and request["action"] in rule["actions"]
            and request["resource"] in rule["resources"]
            and request["environment"] in rule["environments"]
            and ("expires_at" not in rule or now < expires_at(rule["expires_at"]))
        ]
        matched = sorted(rule["id"] for rule in matching)
        if any(rule["effect"] == "deny" for rule in matching):
            reason = "explicit_deny"
        elif any(rule["effect"] == "allow" for rule in matching):
            decision, reason = "allow", "matching_allow_rule"
    return {
        "schema": "agent-economy.action-policy-decision.v1",
        "decision": decision, "reason": reason, "matching_rule_ids": matched,
        "policy_sha256": digest, "principal_authenticated": False,
        "credential_verified": False, "action_executed": False,
        "authorizes_financial_actions": False,
        "note": "Preflight only; caller-supplied principals are not authenticated."
    }

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("request", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(read_strict_json(args.policy), read_strict_json(args.request))
    except (PolicyError, OSError, TypeError, ValueError) as exc:
        result = {
            "schema": "agent-economy.action-policy-decision.v1",
            "decision": "deny", "reason": "invalid_input",
            "error_code": exc.code if isinstance(exc, PolicyError) else "invalid_input",
            "principal_authenticated": False, "credential_verified": False,
            "action_executed": False, "authorizes_financial_actions": False
        }
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    try:
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
    except OSError:
        return 2
    return 0 if result["decision"] == "allow" else 1

if __name__ == "__main__":
    sys.exit(main())
