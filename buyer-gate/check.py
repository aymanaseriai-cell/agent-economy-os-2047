#!/usr/bin/env python3
"""Offline, buyer-pinned acceptance checks for AI-agent deliverables.

A reproducible check against caller-supplied bytes. This program NEVER proves
buyer identity, task execution, provenance, current source freshness or payment.
No external network, executable loading, or private information collection.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

SCHEMA = "agent-economy.buyer-gate/1"
HEX = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,179}$")
ALLOWED = {"file_exists", "file_sha256", "json_pointer_equals", "text_contains"}
MAX_POLICY_BYTES = 64 * 1024
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_REQUIREMENTS = 30


class GateError(ValueError):
    pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def strict_json_loads(content: str):
    """Reject ambiguous or non-standard JSON instead of trusting parser-specific behavior."""
    def unique_keys(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise GateError("DUPLICATE_JSON_KEY")
            out[key] = value
        return out

    def reject_nonfinite(token):
        raise GateError("NONFINITE_JSON_NUMBER")

    return json.loads(content, object_pairs_hook=unique_keys, parse_constant=reject_nonfinite)


def protected_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not SAFE_PATH.fullmatch(relative):
        raise GateError("INVALID_ARTIFACT_PATH")
    if "\\" in relative or "//" in relative or any(x in (".", "..") for x in relative.split("/")):
        raise GateError("INVALID_ARTIFACT_PATH")
    if relative.startswith("/") or relative.startswith(".git/"):
        raise GateError("INVALID_ARTIFACT_PATH")
    base = root.resolve(strict=True)
    current = base
    for segment in relative.split("/"):
        current = current / segment
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            return current
        if stat.S_ISLNK(mode):
            raise GateError("SYMLINK_NOT_ALLOWED")
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise GateError("UNSUPPORTED_ARTIFACT_TYPE")
    resolved = current.resolve(strict=False)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise GateError("ARTIFACT_OUTSIDE_ROOT") from exc
    return current


def byte_artifact(path: Path) -> bytes:
    if not path.is_file():
        raise GateError("MISSING_FILE")
    info = path.stat()
    if info.st_size > MAX_ARTIFACT_BYTES:
        raise GateError("FILE_TOO_LARGE")
    with path.open("rb") as handle:
        data = handle.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise GateError("FILE_TOO_LARGE")
    return data


def pointer_value(obj, pointer: str):
    if not isinstance(pointer, str) or not pointer.startswith("/") or len(pointer) > 150:
        raise GateError("INVALID_JSON_POINTER")
    cursor = obj
    for raw in pointer.split("/")[1:]:
        if re.search(r"~(?![01])", raw):
            raise GateError("INVALID_JSON_POINTER")
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cursor, dict) and key in cursor:
            cursor = cursor[key]
        elif isinstance(cursor, list) and re.fullmatch(r"0|[1-9][0-9]*", key) and int(key) < len(cursor):
            cursor = cursor[int(key)]
        else:
            raise GateError("POINTER_NOT_FOUND")
    return cursor


def load_policy(policy_path: Path, expected_digest: str):
    if not isinstance(expected_digest, str) or not HEX.fullmatch(expected_digest):
        raise GateError("INVALID_POLICY_PIN")
    with policy_path.open("rb") as handle:
        content = handle.read(MAX_POLICY_BYTES + 1)
    if len(content) > MAX_POLICY_BYTES:
        raise GateError("POLICY_TOO_LARGE")
    actual = sha(content)
    if actual != expected_digest:
        raise GateError("POLICY_PIN_MISMATCH")
    try:
        policy = strict_json_loads(content.decode("utf-8"))
    except GateError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise GateError("INVALID_POLICY_JSON") from exc
    if not isinstance(policy, dict) or policy.get("schema") != SCHEMA:
        raise GateError("INVALID_POLICY_SCHEMA")
    reqs = policy.get("requirements")
    if not isinstance(reqs, list) or not (1 <= len(reqs) <= MAX_REQUIREMENTS):
        raise GateError("INVALID_REQUIREMENT_COUNT")
    seen = set()
    for requirement in reqs:
        if not isinstance(requirement, dict):
            raise GateError("INVALID_REQUIREMENT")
        rid = requirement.get("id")
        kind = requirement.get("type")
        if not isinstance(rid, str) or not ID.fullmatch(rid) or rid in seen:
            raise GateError("INVALID_OR_DUPLICATE_ID")
        seen.add(rid)
        if not isinstance(kind, str) or kind not in ALLOWED:
            raise GateError("UNSUPPORTED_REQUIREMENT")
        if not isinstance(requirement.get("path"), str):
            raise GateError("INVALID_ARTIFACT_PATH")
        if kind == "file_sha256" and (
            not isinstance(requirement.get("expected_sha256"), str)
            or not HEX.fullmatch(requirement["expected_sha256"])
        ):
            raise GateError("INVALID_SHA256")
        if kind == "json_pointer_equals":
            pointer = requirement.get("pointer")
            if not isinstance(pointer, str) or not pointer.startswith("/") or len(pointer) > 150:
                raise GateError("INVALID_JSON_POINTER")
            if "expected" not in requirement or isinstance(requirement["expected"], (dict, list)):
                raise GateError("INVALID_EXPECTED_VALUE")
        if kind == "text_contains" and (
            not isinstance(requirement.get("needle"), str)
            or not (1 <= len(requirement["needle"]) <= 100)
        ):
            raise GateError("INVALID_TEXT_NEEDLE")
    return reqs, actual


def check(policy_path: Path, root: Path, expected_policy_digest: str) -> dict:
    report = {
        "schema": "agent-economy.buyer-gate-report/1",
        "policy_sha256": None, "policy_pin_matched": False,
        "local_checks_passed": False, "checked": 0, "results": [],
        "buyer_identity_verified": False, "buyer_authority_verified": False,
        "agent_execution_verified": False, "source_freshness_verified": False,
        "independent_provenance_verified": False, "payment_verified": False,
        "trust_boundary": (
            "A policy hash only anchors to the separately pinned bytes; it does "
            "not establish who pinned them. Results are local file comparisons, "
            "not independent buyer acceptance, execution or certified security."
        ),
    }
    try:
        requirements, actual_policy_hash = load_policy(policy_path, expected_policy_digest)
        report["policy_sha256"] = actual_policy_hash
        report["policy_pin_matched"] = True
        # Fail configuration before reading any input artifact.
        paths = [protected_file(root, r["path"]) for r in requirements]
    except (GateError, OSError) as exc:
        report["errors"] = [str(exc) if isinstance(exc, GateError) else "POLICY_OR_ROOT_IO_ERROR"]
        return report

    for r, path in zip(requirements, paths):
        verdict = {"id": r["id"], "type": r["type"], "path": r["path"], "result": "FAIL"}
        try:
            if r["type"] == "file_exists":
                if not path.is_file():
                    raise GateError("MISSING_FILE")
                if path.stat().st_size > MAX_ARTIFACT_BYTES:
                    raise GateError("FILE_TOO_LARGE")
                verdict["result"] = "PASS"
            else:
                contents = byte_artifact(path)
                if r["type"] == "file_sha256":
                    verdict["result"] = "PASS" if sha(contents) == r["expected_sha256"] else "FAIL"
                elif r["type"] == "text_contains":
                    text = contents.decode("utf-8")
                    verdict["result"] = "PASS" if r["needle"] in text else "FAIL"
                elif r["type"] == "json_pointer_equals":
                    value = pointer_value(strict_json_loads(contents.decode("utf-8")), r["pointer"])
                    verdict["result"] = (
                        "PASS" if type(value) is type(r["expected"]) and value == r["expected"] else "FAIL"
                    )
        except (GateError, OSError, UnicodeError, ValueError) as exc:
            verdict["reason"] = str(exc) if isinstance(exc, GateError) else "INVALID_ARTIFACT_CONTENT"
        report["results"].append(verdict)

    report["checked"] = len(report["results"])
    report["local_checks_passed"] = all(x["result"] == "PASS" for x in report["results"])
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Buyer-pinned AI agent file acceptance gate (offline)")
    p.add_argument("policy", type=Path)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--policy-sha256", required=True, help="Expected hash pinned independently of agent output")
    p.add_argument("--json-out", type=Path)
    args = p.parse_args()
    r = check(args.policy, args.root, args.policy_sha256)
    payload = json.dumps(r, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload, encoding="utf-8")
    print(payload)
    # Hosted GitHub Actions job summary, never infer third-party authority.
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        try:
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as f:
                f.write("### Agent Economy — Buyer-pinned local checks\n\n")
                f.write("Result: **" + ("PASS" if r["local_checks_passed"] else "FAIL") + "**\n\n")
                f.write("Independent provenance, buyer acceptance, source freshness and payment: **NOT VERIFIED**.\n\n")
        except OSError:
            pass
    return 0 if r["local_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
