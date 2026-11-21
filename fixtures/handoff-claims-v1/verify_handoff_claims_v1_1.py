#!/usr/bin/env python3
"""Synthetic four-verdict handoff fixture validator; no network or external anchoring.

Usage: python3 verify_handoff_claims_v1_1.py [handoff_claims_v1_1.json]
An agreeing producer-controlled digest never proves independent provenance.
"""
from __future__ import annotations
import hashlib
import json
import posixpath
import re
import sys
from pathlib import Path

HEX_256 = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = "agent-economy-handoff-claims/1.1"
REQUIRED_CASE_FIELDS = (
    "case_id", "saved_bytes", "saved_digest", "current_bytes", "current_digest",
    "historical_version", "current_version", "anchor_digest", "manifest_paths",
    "expected", "expected_diagnostics",
)
VERDICT_KEYS = ("saved_integrity", "current_freshness", "independent_anchor", "alias_uniqueness")

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def is_sha256(s: object) -> bool:
    return isinstance(s, str) and HEX_256.fullmatch(s) is not None

def safe_unique_posix_paths(values: object) -> bool:
    """Lexical aliases only; no symlink or hardlink checks."""
    if not isinstance(values, list) or not values:
        return False
    normalized: list[str] = []
    for path in values:
        if not isinstance(path, str) or not path.strip() or "\\" in path or "\x00" in path:
            return False
        if path.startswith("/"):
            return False
        normalized_path = posixpath.normpath(path)
        if normalized_path in (".", "..") or normalized_path.startswith("../"):
            return False
        normalized.append(normalized_path)
    return len(normalized) == len(set(normalized))

def classify(case: dict) -> tuple[dict[str, str], dict[str, str]]:
    if not isinstance(case, dict) or not all(k in case for k in REQUIRED_CASE_FIELDS):
        raise ValueError("Case is missing required fields")
    for field in ("case_id", "saved_bytes", "current_bytes", "historical_version", "current_version"):
        if not isinstance(case[field], str) or not case[field]:
            raise ValueError("Field must be a nonempty string: " + field)
    for field in ("saved_digest", "current_digest"):
        if not is_sha256(case[field]):
            raise ValueError("Invalid sha256 field: " + field)
    if case["anchor_digest"] is not None and not is_sha256(case["anchor_digest"]):
        raise ValueError("Invalid anchor_digest")

    saved_match = sha256_text(case["saved_bytes"]) == case["saved_digest"]
    current_match = sha256_text(case["current_bytes"]) == case["current_digest"]
    supplied_reference = case["anchor_digest"]
    # Contradictions can disprove a historical claim, but a matching reference
    # in this fixture does not authenticate external custody or timestamp.
    anchor = (
        "FAIL" if supplied_reference is not None
        and (not saved_match or supplied_reference != case["saved_digest"])
        else "NOT_PROVEN"
    )
    verdicts = {
        "saved_integrity": "PASS" if saved_match else "FAIL",
        "current_freshness": "UNVERIFIED_SOURCE_FRESHNESS",
        "independent_anchor": anchor,
        "alias_uniqueness": "PASS" if safe_unique_posix_paths(case["manifest_paths"]) else "FAIL",
    }
    diagnostics = {"current_snapshot_integrity": "PASS" if current_match else "FAIL"}
    return verdicts, diagnostics

def validate_fixture(path: Path) -> int:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(fixture, dict) or fixture.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported or missing schema_version")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("No test cases")
    seen: set[str] = set()
    errors = 0
    for c in cases:
        if not isinstance(c, dict) or c.get("case_id") in seen:
            raise ValueError("Invalid/duplicate case_id")
        seen.add(c["case_id"])
        actual, diagnostics = classify(c)
        expected = c["expected"]
        exp_diag = c["expected_diagnostics"]
        if set(expected) != set(VERDICT_KEYS) or set(exp_diag) != {"current_snapshot_integrity"}:
            raise ValueError("Incorrect expected-verdict schema: " + c["case_id"])
        ok = actual == expected and diagnostics == exp_diag
        errors += not ok
        print(f"{c['case_id']}: {'PASS' if ok else 'FAIL'}")
        if not ok:
            print(json.dumps({"expected": expected, "actual": actual,
                              "expected_diagnostics": exp_diag, "actual_diagnostics": diagnostics}, sort_keys=True))
    print(f"{len(cases)-errors}/{len(cases)} synthetic cases match expectations")
    print("Trust boundary: no independently authenticated anchor, source freshness, execution or payment claimed.")
    return 0 if errors == 0 else 1

if __name__ == "__main__":
    try:
        path = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).with_name("handoff_claims_v1_1.json")
        sys.exit(validate_fixture(path))
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        sys.exit(2)
