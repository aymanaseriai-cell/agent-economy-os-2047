#!/usr/bin/env python3
"""Deterministic offline marketplace ZIP from explicit approved repository files."""
from __future__ import annotations
import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = Path(__file__).resolve().parent / "buyer-acceptance"
FILES = {
    "SKILL.md": SKILL / "SKILL.md",
    "scripts/check.py": ROOT / "buyer-gate" / "check.py",
    "examples/policy.json": ROOT / "examples" / "buyer-gate" / "policy.json",
    "examples/deliverables/report.json": ROOT / "examples" / "buyer-gate" / "deliverables" / "report.json",
    "LICENSE": ROOT / "LICENSE",
}
OUTPUT = ROOT / "dist" / "agent-economy-buyer-acceptance-0.1.0.zip"


def build(destination: Path) -> str:
    destination = destination.resolve()
    if destination in {p.resolve() for p in FILES.values()}:
        raise ValueError("OUTPUT_MUST_NOT_OVERWRITE_SOURCE")
    payload = {}
    for archive_name, source in FILES.items():
        if source.is_symlink() or not source.is_file():
            raise ValueError("MISSING_OR_SYMLINKED_PACKAGE_FILE:" + archive_name)
        data = source.read_bytes()
        if len(data) > 1_000_000:
            raise ValueError("OVERSIZE_PACKAGE_FILE:" + archive_name)
        payload[archive_name] = data
    if not payload["SKILL.md"].startswith(b"---\nname: agent-economy-buyer-acceptance\n"):
        raise ValueError("INVALID_SKILL_FRONTMATTER")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(payload):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            z.writestr(info, payload[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=OUTPUT)
    a = p.parse_args()
    digest = build(a.out)
    print("MARKETPLACE_ARCHIVE_SHA256=" + digest)
    print("REVIEW_ONLY_NOT_PUBLISHED=" + str(a.out.resolve()))


if __name__ == "__main__":
    main()
