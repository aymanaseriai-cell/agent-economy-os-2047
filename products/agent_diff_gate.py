#!/usr/bin/env python3
"""Bounded, offline JSON change gate for agent-delivered artifacts.

A separately pinned SHA-256 binds the caller's approved baseline bytes.
This tool cannot authenticate who pinned those bytes or approve delivery.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

MAX_BYTES = 512 * 1024
MAX_CHANGES = 4000
MAX_DEPTH = 32
DIGEST = re.compile(r"[0-9a-fA-F]{64}\Z")


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _reject_json_constant(value):
    raise ValueError("non-standard JSON constant")


def _read(path: Path):
    if not path.is_file():
        raise ValueError("JSON input is not a regular file")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("JSON input exceeds 512 KiB limit")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("JSON input exceeds 512 KiB limit")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys,
                            parse_constant=_reject_json_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid UTF-8 JSON input") from exc
    return parsed, hashlib.sha256(raw).hexdigest()


def _segment(key: str) -> str:
    return str(key).replace("~", "~0").replace("/", "~1")


def _walk(before, after, pointer, out, depth):
    if depth > MAX_DEPTH:
        raise ValueError("JSON nesting exceeds 32 levels")
    if len(out) >= MAX_CHANGES:
        raise ValueError("more than 4000 differences")
    if type(before) is not type(after):
        out.append(("changed", pointer or "/"))
    elif isinstance(before, dict):
        keys = sorted(set(before) | set(after))
        for key in keys:
            dest = pointer + "/" + _segment(key)
            if key not in before:
                out.append(("added", dest))
            elif key not in after:
                out.append(("removed", dest))
            else:
                _walk(before[key], after[key], dest, out, depth + 1)
            if len(out) > MAX_CHANGES:
                raise ValueError("more than 4000 differences")
    elif isinstance(before, list):
        for idx in range(max(len(before), len(after))):
            dest = pointer + "/" + str(idx)
            if idx >= len(before):
                out.append(("added", dest))
            elif idx >= len(after):
                out.append(("removed", dest))
            else:
                _walk(before[idx], after[idx], dest, out, depth + 1)
            if len(out) > MAX_CHANGES:
                raise ValueError("more than 4000 differences")
    elif before != after:
        out.append(("changed", pointer or "/"))


def _allowed(pointer: str, prefixes: list[str]) -> bool:
    return any(pointer == p or pointer.startswith(p + "/") for p in prefixes)


def evaluate(baseline: Path, candidate: Path, baseline_sha256: str,
             allow_prefixes: list[str] | None = None) -> dict:
    allow_prefixes = allow_prefixes or []
    if not isinstance(baseline_sha256, str) or not DIGEST.fullmatch(baseline_sha256):
        raise ValueError("a separately pinned 64-hex baseline SHA-256 is required")
    if any(not isinstance(p, str) or not p.startswith("/") or p == "/" or "//" in p
           for p in allow_prefixes):
        raise ValueError("allowed pointers must be non-root JSON pointer prefixes")
    previous, previous_digest = _read(baseline)
    if previous_digest.lower() != baseline_sha256.lower():
        return {
            "passed": False, "reason": "BASELINE_DIGEST_MISMATCH",
            "baseline_digest_matches": False,
            "baseline_sha256": previous_digest,
            "candidate_sha256": None, "changed": [],
            "independent_buyer_approval_verified": False,
            "agent_execution_verified": False, "payment_verified": False
        }
    next_value, next_digest = _read(candidate)
    changes: list[tuple[str, str]] = []
    _walk(previous, next_value, "", changes, 0)
    report_changes = [
        {"change": kind, "path": path, "allowed": _allowed(path, allow_prefixes)}
        for kind, path in changes
    ]
    blocked = sum(not item["allowed"] for item in report_changes)
    return {
        "passed": blocked == 0,
        "reason": "PASS" if blocked == 0 else "UNAPPROVED_CHANGE",
        "baseline_digest_matches": True,
        "baseline_sha256": previous_digest,
        "candidate_sha256": next_digest,
        "changed": report_changes,
        "change_count": len(report_changes),
        "blocked_count": blocked,
        "independent_buyer_approval_verified": False,
        "agent_execution_verified": False,
        "payment_verified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed offline JSON change gate for agent-delivered artifacts"
    )
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--allow-prefix", action="append", default=[])
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.baseline, args.candidate, args.baseline_sha256,
                          args.allow_prefix)
    except (OSError, ValueError, RecursionError) as exc:
        report = {
            "passed": False, "reason": "INVALID_INPUT",
            "error": str(exc), "independent_buyer_approval_verified": False,
            "agent_execution_verified": False, "payment_verified": False,
        }
    output = json.dumps(report, indent=2, ensure_ascii=False)
    print(output)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(output + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
