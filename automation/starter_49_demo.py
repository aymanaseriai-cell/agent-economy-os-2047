#!/usr/bin/env python3
"""Reproducible *synthetic* buyer-output starter, entirely offline, no purchases.

This is a demonstration of local checks and of a local policy hash mismatch.
The pinned policy hash here is calculated from the same checkout as a SMOKE TEST,
so it is NOT independent buyer authorization or a production trust root.
"""
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "buyer-gate"
GATE_PATH = ROOT / "buyer-gate" / "check.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("agent_economy_buyer_gate_demo", GATE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("buyer_gate_not_loadable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_demo():
    gate = load_gate()
    policy = EXAMPLE / "policy.json"
    expected_sha = hashlib.sha256(policy.read_bytes()).hexdigest()
    baseline = gate.check(policy, EXAMPLE, expected_sha)
    with tempfile.TemporaryDirectory(prefix="agent-economy-starter-") as tmp:
        root = Path(tmp)
        (root / "deliverables").mkdir()
        trial_policy = root / "policy.json"
        shutil.copyfile(policy, trial_policy)
        saved = EXAMPLE / "deliverables" / "report.json"
        trial_artifact = root / "deliverables" / "report.json"
        original = saved.read_text(encoding="utf-8")
        if '"ready_for_review"' not in original:
            raise ValueError("unexpected_fixture_status")
        trial_artifact.write_text(
            original.replace('"ready_for_review"', '"tampered_status"', 1),
            encoding="utf-8",
        )
        mutated_output = gate.check(trial_policy, root, expected_sha)
        # Reset artifact, then simulate agent replacing the policy without
        # independently updating the buyer's previously held digest.
        trial_artifact.write_text(original, encoding="utf-8")
        original_policy = trial_policy.read_bytes()
        if b'"ready_for_review"' not in original_policy:
            raise ValueError("unexpected_fixture_policy")
        trial_policy.write_bytes(original_policy.replace(b'"ready_for_review"', b'"tampered_status"', 1))
        swapped_policy = gate.check(trial_policy, root, expected_sha)

    tamper_rejected = (
        mutated_output.get("local_checks_passed") is False
        and any(x.get("result") == "FAIL" for x in mutated_output.get("results", []))
    )
    policy_rejected = (
        swapped_policy.get("local_checks_passed") is False
        and swapped_policy.get("policy_pin_matched") is False
        and "POLICY_PIN_MISMATCH" in swapped_policy.get("errors", [])
    )
    result = {
        "schema": "agent-economy.starter-49-demo.v1",
        "ok": baseline.get("local_checks_passed") is True and tamper_rejected and policy_rejected,
        "baseline": {"passed": baseline.get("local_checks_passed"),
                     "checked": baseline.get("checked")},
        "tampered_artifact": {"rejected": tamper_rejected,
                             "checked": mutated_output.get("checked")},
        "swapped_policy": {"rejected": policy_rejected,
                           "reason": swapped_policy.get("errors", [])},
        "policy_digest_sha256": expected_sha,
        "policy_digest_source": "same_checkout_local_smoke_only",
        "customer_identity_verified": False,
        "buyer_authority_verified": False,
        "independent_provenance_verified": False,
        "external_freshness_verified": False,
        "paid_delivery_verified": False,
        "commercial_revenue_verified": False,
        "network_calls": 0,
        "payment_calls": 0,
        "trust_limit": "Checks are synthetic local file comparisons, not authorized buyer pinning, real agent execution or an actual customer delivery.",
    }
    return result


def main():
    result = run_demo()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
