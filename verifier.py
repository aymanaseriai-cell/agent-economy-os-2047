#!/usr/bin/env python3
"""Offline evidence-file integrity validator (stdlib only).

Checks that declared artifacts exist inside --root and match their sha256.
This establishes file integrity relative to a manifest, not identity,
authenticity, model quality, or real-world truth.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def reject_duplicate_keys(pairs):
    """Reject ambiguous JSON objects at any nesting depth (fail closed)."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_non_json_constant(value):
    """Refuse NaN and Infinity tokens, which are invalid JSON."""
    raise ValueError(f"non-standard JSON constant: {value}")


def validate(manifest_path: Path, root: Path) -> dict:
    root = root.resolve()
    errors = []
    results = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys, parse_constant=reject_non_json_constant)
    except (OSError, UnicodeError, ValueError) as exc:
        return {"passed": False, "checked": 0, "artifacts": [], "errors": [f"Could not read manifest: {exc}"]}

    records = manifest.get("artifacts") if isinstance(manifest, dict) else None
    if not isinstance(records, list) or not records:
        return {"passed": False, "checked": 0, "artifacts": [], "errors": ["Manifest must contain a non-empty 'artifacts' array"]}

    # Reject lexical and symlink aliases that resolve to the same artifact.
    seen_paths = {}
    for idx, record in enumerate(records):
        label = f"artifacts[{idx}]"
        if not isinstance(record, dict):
            errors.append(f"{label}: expected object")
            continue
        relative = record.get("path")
        expected = record.get("sha256")
        if not isinstance(relative, str) or not relative.strip() or not isinstance(expected, str) or not SHA256.fullmatch(expected):
            errors.append(f"{label}: expected non-empty path and 64-character sha256")
            continue
        try:
            path = (root / relative).resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"{label}: cannot resolve artifact path: {relative}: {exc}")
            continue
        try:
            path.relative_to(root)
        except ValueError:
            errors.append(f"{label}: path escapes project root")
            continue
        if path in seen_paths:
            first_index, first_label = seen_paths[path]
            errors.append(
                f"{label}: duplicate canonical artifact path: {relative} "
                f"(same as artifacts[{first_index}]: {first_label})"
            )
            continue
        seen_paths[path] = (idx, relative)
        if not path.is_file():
            errors.append(f"{label}: file not found: {relative}")
            continue
        try:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            actual = digest.hexdigest()
        except OSError as exc:
            errors.append(f"{label}: cannot read file: {exc}")
            continue
        matched = actual.lower() == expected.lower()
        results.append({"path": relative, "sha256": actual, "matched": matched})
        if not matched:
            errors.append(f"{label}: sha256 mismatch: {relative}")
    return {"passed": not errors, "checked": len(results), "artifacts": results, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Verify local AI-agent evidence artifacts against SHA256 manifest")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--json-out", type=Path, help="Optional report file")
    args = parser.parse_args()
    report = validate(args.manifest, args.root)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    print(payload)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
