#!/usr/bin/env python3
"""Opt-in synthetic proof-of-value reply to public Issue Forms, not customer audit."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures" / "handoff-claims-v1"
if str(FIXTURE_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURE_DIR))
from verify_handoff_claims_v1_1 import classify

PREFIX = "[Evidence challenge]"
CONSENT = "I understand this public automated answer uses only synthetic evidence, not my private system."
MARKER = "<!-- agent-economy-automated-response-v1 -->"
FIXTURE_REF = "d8fa41120ab33f844426051aab35894e34c26824"
FIXTURE_URL = "https://github.com/aymanaseriai-cell/agent-economy-os-2047/blob/" + FIXTURE_REF + "/fixtures/handoff-claims-v1/README.md"
PILOT_URL = "https://github.com/aymanaseriai-cell/agent-economy-os-2047/blob/main/docs/ENTERPRISE_EVIDENCE_PILOT.md"
REQUEST_URL = "https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=service-request.yml"

SCENARIOS = {
    "Saved output changed, reference digest was not updated": (
        "tamper_a_bytes_only", "Saved bytes no longer match the digest supplied by the producer.",
        "Keep an independently retained reference for the expected artifact."
    ),
    "Output and self-reported digest both changed": (
        "tamper_b_bytes_and_self_digest", "Self-consistency cannot establish independent provenance.",
        "Pin trusted acceptance criteria and source evidence outside the producer's control."
    ),
    "Supplied reference contradicts the saved claim": (
        "reference_matches_bytes_but_not_declared_digest",
        "A supplied reference matches modified raw bytes but not the declared saved digest: the composite saved claim fails closed.",
        "Check byte/digest/reference agreement and independently authenticate reference custody."
    ),
    "A synthetic snapshot is misrepresented as live freshness": (
        "current_snapshot_changed_without_digest", "A synthetic digest or version label does not prove real source freshness.",
        "Independently fetch the source and apply an explicit recency acceptance rule."
    ),
    "Two declared artifact paths are the same lexical file": (
        "duplicate_canonical_alias", "Lexical aliases can double-count one submitted artifact.",
        "Deduplicate resolved paths and separately test symlink, hardlink and race cases."
    ),
}
STEPS = {
    "Show me the free synthetic demonstration only",
    "Explore a scoped enterprise pilot (no payment)",
    "I have a public technical review question",
}
KEYS = ("saved_integrity", "current_freshness", "independent_anchor", "alias_uniqueness")

def form_value(body, heading):
    if not isinstance(body, str) or len(body) > 16000:
        return None
    match = re.search(
        r"(?mi)^### " + re.escape(heading) + r"[ \t]*\r?\n(?:[ \t]*\r?\n)*([^\r\n]+)",
        body,
    )
    return match.group(1).strip() if match else None

def is_opted_in(body):
    return isinstance(body, str) and bool(re.search(
        r"(?mi)^-\s*\[[xX]\]\s*" + re.escape(CONSENT) + r"\s*$", body
    ))

def load_verified_case(case_id, fixture=None):
    if fixture is None:
        fixture = json.loads((FIXTURE_DIR / "handoff_claims_v1_1.json").read_text(encoding="utf-8"))
    if not isinstance(fixture, dict) or fixture.get("schema_version") != "agent-economy-handoff-claims/1.1":
        raise ValueError("Incorrect fixture schema")
    cases = fixture.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Missing synthetic cases")
    found = [c for c in cases if isinstance(c, dict) and c.get("case_id") == case_id]
    if len(found) != 1:
        raise ValueError("Synthetic case is missing or not unique")
    case = found[0]
    verdicts, diag = classify(case)
    if verdicts != case.get("expected") or diag != case.get("expected_diagnostics"):
        raise ValueError("Fixture mismatch: aborting public result")
    return verdicts, diag

def build_evidence_response(issue):
    if not isinstance(issue, dict) or not str(issue.get("title", "")).startswith(PREFIX):
        return None
    body = issue.get("body")
    if not is_opted_in(body):
        return None
    choice = form_value(body, "Evidence failure to explore")
    step = form_value(body, "Preferred next step")
    if choice not in SCENARIOS or step not in STEPS:
        return None
    case_id, interpretation, improvement = SCENARIOS[choice]
    verdicts, diag = load_verified_case(case_id)
    parts = [
        MARKER,
        "### Opt-in free synthetic evidence check",
        "",
        "Automated response based solely on a committed public fixture. Your agent, repository and production data were NOT inspected.",
        "",
        "**Chosen failure:** " + choice,
        "**Fixed test ID:** " + case_id,
        "",
        "| Technical claim | Recomputed synthetic result |",
        "| --- | --- |",
    ]
    for key in KEYS:
        parts.append("| " + key + " | " + verdicts[key] + " |")
    parts.append("| current_snapshot_integrity (diagnostic only) | " + diag["current_snapshot_integrity"] + " |")
    parts += [
        "",
        "**Finding:** " + interpretation,
        "**Buyer-side acceptance control:** " + improvement,
        "",
        "Reproduction: [version-pinned fixture and commands](" + FIXTURE_URL + ").",
        "Boundary: freshness is never verified by this synthetic dataset. Digest agreement cannot prove external authorship, task execution, independent custody, payment or buyer acceptance.",
        "",
    ]
    if step == "Explore a scoped enterprise pilot (no payment)":
        parts += [
            "**Optional business next step:** Review the [limited pilot scope](" + PILOT_URL + ") and submit a [public non-sensitive service request](" + REQUEST_URL + ") only if relevant.",
            "USD $750 is an indicative, non-binding hypothesis, NOT a checkout, contract or request for money. A lawful payment method, invoicing and scope would need separate agreement.",
            "**One question:** What precise buyer acceptance requirement would this evidence gap violate in your workflow?",
        ]
    elif step == "I have a public technical review question":
        parts.append("You may respond here with a public/synthetic counterexample. A technical question is not an agreement to buy.")
    else:
        parts.append("No follow-up required. You can reproduce the synthetic result offline before deciding whether it is relevant.")
    parts += [
        "",
        "**Public issue safety:** Never post API keys, credentials, private client data, wallet signatures, transaction authorization or confidential source. No customer certification or paid revenue is claimed.",
    ]
    return "\n".join(parts)
