"""Offline preflight of selected A2A v1 Agent Card fields.
This is NOT full protocol conformance, live identity verification, or a signature check.
Original implementation based on publicly documented A2A metadata requirements.
"""
import argparse
import ipaddress
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

MAX_INPUT = 262144

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result

def good_text(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip() and len(value) <= 1024

def public_https(value):
    if not good_text(value) or len(value) > 2048:
        return False
    try:
        p = urlsplit(value)
        if p.scheme != "https" or not p.hostname or p.username is not None or p.password is not None or p.fragment or p.port not in (None, 443):
            return False
        host = p.hostname.rstrip(".").lower()
        if host in ("localhost", "local", "invalid", "test") or host.endswith((".localhost", ".local", ".internal", ".invalid", ".test")):
            return False
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_global
        except ValueError:
            parts = host.split(".")
            return len(parts) >= 2 and all(part and part.replace("-", "").isalnum() and not part.startswith("-") and not part.endswith("-") for part in parts)
    except (TypeError, ValueError):
        return False

def public_grpc_address(value):
    """Validate a public gRPC host:port binding without DNS or network access."""
    if not good_text(value) or len(value) > 255 or any(c in value for c in "/?#@\\ \t\n"):
        return False
    host, separator, port = value.rpartition(":")
    if not separator or not port.isascii() or not port.isdecimal() or len(port) > 5:
        return False
    if not (1 <= int(port) <= 65535):
        return False
    if host.startswith("[") and host.endswith("]"):
        try:
            return ipaddress.ip_address(host[1:-1]).is_global
        except ValueError:
            return False
    # Same public hostname restrictions as HTTPS interfaces. The synthetic
    # URL is validated locally; it is NEVER contacted.
    return public_https("https://" + host)

def audit(card):
    failures, warnings = [], []
    def fail(code, path):
        failures.append({"code": code, "path": path})
    def warn(code, path):
        warnings.append({"code": code, "path": path})
    if not isinstance(card, dict):
        fail("invalid_card", "$")
    else:
        for field in ("name", "description", "version"):
            if not good_text(card.get(field)):
                fail("required_text", "$." + field)
        interfaces = card.get("supportedInterfaces")
        if not isinstance(interfaces, list) or not (1 <= len(interfaces) <= 32):
            fail("required_interfaces", "$.supportedInterfaces")
            if "url" in card or "protocolVersion" in card:
                warn("legacy_card_shape_unverified", "$")
        else:
            for i, item in enumerate(interfaces):
                path = "$.supportedInterfaces[" + str(i) + "]"
                if not isinstance(item, dict):
                    fail("invalid_interface", path)
                    continue
                for field in ("protocolBinding", "protocolVersion"):
                    if not good_text(item.get(field)):
                        fail("required_text", path + "." + field)
                if not (public_grpc_address(item.get("url")) if item.get("protocolBinding") == "GRPC" else public_https(item.get("url"))):
                    fail("unsafe_interface_url", path + ".url")
        caps = card.get("capabilities")
        if not isinstance(caps, dict):
            fail("required_capabilities", "$.capabilities")
        else:
            for key in ("streaming", "pushNotifications", "extendedAgentCard"):
                if key in caps and not isinstance(caps[key], bool):
                    fail("invalid_capability", "$.capabilities." + key)
        for field in ("defaultInputModes", "defaultOutputModes"):
            modes = card.get(field)
            if not isinstance(modes, list) or not (1 <= len(modes) <= 64) or any(not good_text(x) or "/" not in x for x in modes):
                fail("required_mime_modes", "$." + field)
        skills = card.get("skills")
        if not isinstance(skills, list) or len(skills) > 128:
            fail("required_skills_array", "$.skills")
        else:
            seen = set()
            for i, skill in enumerate(skills):
                path = "$.skills[" + str(i) + "]"
                if not isinstance(skill, dict):
                    fail("invalid_skill", path)
                    continue
                for key in ("id", "name", "description"):
                    if not good_text(skill.get(key)):
                        fail("invalid_skill_field", path + "." + key)
                ident = skill.get("id")
                if isinstance(ident, str):
                    if ident in seen:
                        fail("duplicate_skill_id", path + ".id")
                    seen.add(ident)
                tags = skill.get("tags")
                if not isinstance(tags, list) or not tags or len(tags) > 64 or any(not good_text(tag) for tag in tags):
                    fail("invalid_skill_tags", path + ".tags")
        if "securitySchemes" in card and not isinstance(card["securitySchemes"], dict):
            fail("invalid_security_schemes", "$.securitySchemes")
        if "signatures" in card:
            warn("signatures_not_verified", "$.signatures")
    warn("metadata_only_not_conformance_or_identity", "$")
    return {
        "schema": "agent-economy.a2a-card-preflight.v1",
        "status": "preflight_failed" if failures else "preflight_passed",
        "failures": failures,
        "warnings": warnings,
        "identity_verified": False,
        "signature_verified": False,
        "network_requests_made": False,
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card", type=Path, help="A local JSON file; no URL fetch is performed")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    try:
        if args.card.stat().st_size > MAX_INPUT:
            raise ValueError("file exceeds 256 KiB")
        card = json.loads(args.card.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
        report = audit(card)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        report = {"schema": "agent-economy.a2a-card-preflight.v1", "status": "preflight_failed", "failures": [{"code": "invalid_input", "message": str(exc)[:300]}], "warnings": [], "identity_verified": False, "signature_verified": False, "network_requests_made": False}
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if report["status"] == "preflight_passed" else 1

if __name__ == "__main__":
    sys.exit(main())
