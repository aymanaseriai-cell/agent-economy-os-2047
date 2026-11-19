#!/usr/bin/env python3
"""Offline evidence-file integrity validator (stdlib only).

Checks that declared artifacts exist inside --root and match their sha256.
This establishes file integrity relative to a manifest, not identity,
authenticity, model quality, or real-world truth.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PureWindowsPath

SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")



def _components(relative: str) -> tuple[str, ...]:
    """Reject ambiguous or platform-specific paths before touching the filesystem."""
    if (not relative or relative.strip() != relative or "\\" in relative
            or "\x00" in relative or Path(relative).is_absolute()
            or PureWindowsPath(relative).is_absolute()
            or PureWindowsPath(relative).drive):
        raise ValueError("path escapes project root or is not a portable relative path")
    parts = tuple(relative.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("path escapes project root or contains ambiguous segments")
    return parts


def _open_regular(root: Path, parts: tuple[str, ...]):
    """Use dirfd/no-follow on POSIX to reject symlink traversal and non-regular files."""
    if os.name == "posix" and hasattr(os, "O_NOFOLLOW"):
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        directory_flags = flags | os.O_DIRECTORY
        directory_fd = os.open(root, directory_flags)
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = next_fd
            file_fd = os.open(parts[-1], flags | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
            try:
                item_stat = os.fstat(file_fd)
                if not stat.S_ISREG(item_stat.st_mode):
                    raise ValueError("artifact is not a regular file")
                return os.fdopen(file_fd, "rb"), item_stat
            except BaseException:
                os.close(file_fd)
                raise
        finally:
            os.close(directory_fd)
    # Windows fallback: refuse symlinks and verify resolved containment.
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("symlink artifacts are not accepted")
    if not path.resolve().is_relative_to(root):
        raise ValueError("path escapes project root")
    handle = path.open("rb")
    item_stat = os.fstat(handle.fileno())
    if not stat.S_ISREG(item_stat.st_mode):
        handle.close()
        raise ValueError("artifact is not a regular file")
    return handle, item_stat


def validate(manifest_path: Path, root: Path) -> dict:
    root = root.resolve()
    errors = []
    results = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"passed": False, "checked": 0, "artifacts": [], "errors": [f"Could not read manifest: {exc}"]}

    records = manifest.get("artifacts") if isinstance(manifest, dict) else None
    if not isinstance(records, list) or not records:
        return {"passed": False, "checked": 0, "artifacts": [], "errors": ["Manifest must contain a non-empty 'artifacts' array"]}

    seen_paths = set()
    seen_files = set()
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
            parts = _components(relative)
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
            continue
        if parts in seen_paths:
            errors.append(f"{label}: duplicate artifact path: {relative}")
            continue
        seen_paths.add(parts)
        try:
            handle, file_stat = _open_regular(root, parts)
            with handle:
                inode = (file_stat.st_dev, file_stat.st_ino)
                if inode in seen_files:
                    errors.append(f"{label}: duplicate underlying file: {relative}")
                    continue
                seen_files.add(inode)
                digest = hashlib.sha256()
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
                actual = digest.hexdigest()
        except (OSError, ValueError) as exc:
            errors.append(f"{label}: cannot read regular artifact {relative}: {exc}")
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
