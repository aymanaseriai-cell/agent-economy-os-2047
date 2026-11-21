"""Offline synthetic claim-boundary demonstration; not an attestation or live-source check."""
import argparse
import hashlib
import json
import posixpath
import re
from pathlib import Path

SCHEMA = "agent-economy.claim-boundaries.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _digest(value):
    if not isinstance(value, bytes):
        raise TypeError("input snapshots must be raw bytes")
    return hashlib.sha256(value).hexdigest()


def _canonical_paths(paths):
    if not isinstance(paths, (tuple, list)) or not 1 <= len(paths) <= 16:
        raise ValueError("paths must contain 1..16 relative entries")
    normalized = []
    for path in paths:
        if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
            raise ValueError("invalid POSIX artifact path")
        if path.startswith("/") or ".." in path.split("/"):
            raise ValueError("artifact path must be relative and contained")
        canonical = posixpath.normpath(path)
        if canonical in (".", ""):
            raise ValueError("artifact path must identify a file")
        normalized.append(canonical)
    return normalized


def assess(*, saved, current, tampered, reference_sha256, paths):
    """Compare bytes with a caller-supplied reference; never infer an external trust anchor."""
    if not isinstance(reference_sha256, str) or not _SHA256.fullmatch(reference_sha256):
        raise ValueError("reference_sha256 must be 64 lowercase hexadecimal characters")
    saved_sha = _digest(saved)
    current_sha = _digest(current)
    tampered_sha = _digest(tampered)
    normalized = _canonical_paths(paths)
    has_alias = len(normalized) != len(set(normalized))
    return {
        "schema": SCHEMA,
        "synthetic": True,
        "claims": {
            "saved_integrity": {
                "verdict": "PASS" if saved_sha == reference_sha256 else "FAIL",
                "sha256": saved_sha,
                "reference_sha256": reference_sha256,
                "reference_trust": "CALLER_SUPPLIED_UNVERIFIED",
            },
            "current_freshness": {
                "verdict": "NOT_PROVEN",
                "different_snapshot_observed": current_sha != saved_sha,
                "snapshot_sha256": current_sha,
                "reason": "A supplied snapshot is not an independently authenticated live read.",
            },
            "independent_anchor": {
                "verdict": "NOT_PROVEN",
                "reason": "No separately verified external signature, timestamp or append-only anchor.",
            },
            "alias_uniqueness": {
                "verdict": "FAIL_CLOSED" if has_alias else "PASS",
                "canonical_paths": normalized,
                "scope": "lexical POSIX aliases only; symlinks and hardlinks not assessed",
            },
        },
        "adversarial": {
            "tamper_a": {
                "verdict": "DETECTED" if tampered_sha != reference_sha256 else "NOT_DETECTED",
                "reason": "Altered bytes compared to unchanged caller-supplied reference",
            },
            "tamper_b": {
                "verdict": "NOT_PROVEN",
                "producer_self_consistency": True,
                "fails_caller_reference": tampered_sha != reference_sha256,
                "reason": "Producer can replace both bytes and its own digest; self-consistency is not anchoring",
            },
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline synthetic source-claim boundaries")
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--reference-sha256", required=True)
    parser.add_argument("--paths", nargs="+", default=["positive.json", "./positive.json"])
    a = parser.parse_args(argv)
    result = assess(
        saved=(a.fixture_dir / "saved.txt").read_bytes(),
        current=(a.fixture_dir / "current.txt").read_bytes(),
        tampered=(a.fixture_dir / "tampered.txt").read_bytes(),
        reference_sha256=a.reference_sha256,
        paths=a.paths,
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

