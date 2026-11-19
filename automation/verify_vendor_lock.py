#!/usr/bin/env python3
"""Offline SHA-256 integrity check for pinned Apache-2.0 A2A vendor files.

This confirms local bytes match the reviewed lockfile, NOT the authenticity
of the upstream repository or legitimacy of the lockfile's author.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

SCHEMA = "agent-economy.vendor-integrity.v1"
REQUIRED = frozenset({
    "specification/a2a.proto",
    "fixtures/air_ticketing_agent.json",
    "fixtures/currency_agent.json",
    "LICENSE",
})
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

def duplicate_keys(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate_json_key")
        output[key] = value
    return output

def check(root, lock):
    problems = []
    if (not isinstance(lock, dict) or set(lock) != {"schema", "assets"}
            or lock.get("schema") != SCHEMA or not isinstance(lock.get("assets"), list)):
        return {"ok": False, "verified": 0, "errors": ["invalid_lock_schema"]}
    expected = set()
    verified = 0
    for asset in lock["assets"]:
        if not isinstance(asset, dict) or set(asset) != {
            "path", "upstream_repository", "source_commit", "source_path", "sha256", "license"
        }:
            problems.append("invalid_asset_schema")
            continue
        name = asset["path"]
        if not isinstance(name, str) or name not in REQUIRED or name in expected:
            problems.append("unexpected_or_duplicate_asset")
            continue
        expected.add(name)
        if (asset["license"] != "Apache-2.0"
                or not isinstance(asset["source_commit"], str)
                or not COMMIT.fullmatch(asset["source_commit"])
                or not isinstance(asset["sha256"], str)
                or not SHA256.fullmatch(asset["sha256"])
                or not isinstance(asset["upstream_repository"], str)
                or asset["upstream_repository"] not in ("a2aproject/A2A", "a2aproject/a2a-samples")
                or not isinstance(asset["source_path"], str)
                or not asset["source_path"].startswith(("specification/", "samples/", "LICENSE"))
                or ".." in asset["source_path"]):
            problems.append("invalid_provenance:" + name)
            continue
        # Paths are confined to a hardcoded allow-list; never trust the lock as a path source.
        root_path = (Path(root) / "third_party" / "a2a").resolve()
        location = root_path / name
        if location.is_symlink() or not location.is_file() or not location.resolve().is_relative_to(root_path):
            problems.append("missing_or_unsafe_file:" + name)
            continue
        if location.stat().st_size > 262144:
            problems.append("oversized_file:" + name)
            continue
        digest = hashlib.sha256(location.read_bytes()).hexdigest()
        if digest != asset["sha256"]:
            problems.append("sha256_mismatch:" + name)
            continue
        verified += 1
    if expected != REQUIRED:
        problems.append("required_assets_missing")
    return {"ok": not problems, "verified": verified, "errors": sorted(set(problems)),
            "trust": "local_file_bytes_match_reviewed_lock_only",
            "upstream_identity_verified": False}

def main():
    repo_root = Path(__file__).resolve().parents[1]
    filename = repo_root / "third_party/a2a/VENDOR_LOCK.json"
    try:
        if filename.stat().st_size > 16384:
            raise ValueError("lock_too_large")
        lock = json.loads(filename.read_text(encoding="utf-8"), object_pairs_hook=duplicate_keys)
        result = check(repo_root, lock)
    except (OSError, UnicodeError, ValueError, RecursionError):
        result = {"ok": False, "verified": 0, "errors": ["invalid_lock_input"]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1

if __name__ == "__main__":
    sys.exit(main())
