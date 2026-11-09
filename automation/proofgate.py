#!/usr/bin/env python3
"""ProofGate: fail-closed public paid-gig preflight for Agent Economy OS 2047.

No wallets, private credentials, paid calls, signups, outreach or external code execution.
Aggregator metadata is *not* independently verified escrow or buyer intent.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler

FEED_URL = "https://jobbi.org/gigs.json?lane=agent&limit=2000"
FEED_HOST = "jobbi.org"
MAX_BYTES = 2_000_000
MAX_ITEMS = 2000
MAX_RESULTS = 20

# Keywords match a narrow set of services we already know how to fulfill.
CAPABILITIES = {
    "evidence_integrity": (("evidence", 9), ("sha256", 9), ("provenance", 7), ("receipt", 6), ("verification", 4)),
    "api_quality_assurance": (("api", 5), ("qa", 8), ("testing", 5), ("reproducible", 6), ("audit", 5), ("regression", 6)),
    "developer_automation": (("python", 5), ("github", 5), ("ci/cd", 5), ("workflow", 5), ("automation", 4), ("script", 3)),
    "agent_interoperability": (("agent", 3), ("x402", 6), ("mcp", 6), ("a2a", 5), ("usdc", 3), ("integration", 4)),
}
# These require actions or payments we cannot safely or honestly commit to.
HARD_BLOCK = (
    "pay a registration", "deposit first", "purchase a", "pay to join",
    "send usdc first", "buy tokens", "guaranteed returns",
    "followers", "likes and retweets", "cold dm", "mass email",
    "create a paid", "post a paid", "seed a paid", "child bounty",
    "buy a paid", "payment upfront", "upfront fee", "wallet minting",
    "industrial sentinel", "install a container", "run a container",
    "generate paid revenue before", "pre-funded sale",
    "exploit", "steal credentials", "bypass authentication",
)
SOURCE_HOSTS = frozenset((
    "api.basedagents.ai", "api.bountybook.ai", "api.agentbounties.app",
    "opentask.ai", "swarmmemo.com",
))
SAFE_URL = re.compile(r"^https://[a-zA-Z0-9._~/%?=&+:#@-]{1,1000}$")
WORDS = re.compile(r"[a-z0-9]+(?:/[a-z0-9]+)*")
GRADE = {"A+": 5, "A": 4, "A-": 3, "B+": 2, "B": 1}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


def http_read(url: str, max_bytes: int = MAX_BYTES) -> tuple[int, bytes]:
    """Bounded GET with no redirect following and no authentication headers."""
    opener = build_opener(NoRedirect)
    req = Request(url, headers={"User-Agent": "AgentEconomy-ProofGate/1.0",
                                "Accept": "application/json"})
    try:
        with opener.open(req, timeout=15) as resp:
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("response_exceeds_limit")
            return resp.status, data
    except HTTPError as exc:
        return exc.code, b""


def bounded_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "")[:limit]


def host_allowed(url: str, hosts: frozenset[str]) -> bool:
    if not isinstance(url, str) or not SAFE_URL.fullmatch(url):
        return False
    try:
        p = urlsplit(url)
        return (p.scheme == "https" and p.hostname in hosts
                and p.username is None and p.password is None
                and p.port in (None, 443))
    except ValueError:
        return False


def classify(item: object, today: dt.date) -> tuple[dict | None, str]:
    if not isinstance(item, dict):
        return None, "malformed_item"
    meta = item.get("_jobbi")
    if not isinstance(meta, dict):
        return None, "missing_aggregator_metadata"
    reward = meta.get("reward")
    if not isinstance(reward, dict):
        return None, "missing_reward"
    if meta.get("lane") != "agent" or meta.get("claims_open") is not True:
        return None, "closed_or_wrong_lane"
    if reward.get("currency") != "USDC":
        return None, "unsupported_payout_currency"
    try:
        amount = float(reward.get("amount"))
    except (ValueError, TypeError):
        return None, "invalid_amount"
    if not 0 < amount <= 100_000:
        return None, "invalid_amount"
    rail = reward.get("rail")
    if rail not in ("usdc-base", "x402", "wallet"):
        return None, "unsupported_payout_rail"

    expires = meta.get("expires")
    if expires:
        try:
            expiry = dt.datetime.fromisoformat(str(expires).replace("Z", "+00:00")).date()
        except ValueError:
            return None, "malformed_expiry"
        if expiry < today:
            return None, "expired"

    title = bounded_text(item.get("title"), 180)
    body = bounded_text(item.get("content_text"), 2000)
    url = bounded_text(item.get("url"), 1000)
    if not host_allowed(url, frozenset(SOURCE_HOSTS | {
        "github.com", "bountybook.ai", "basedagents.ai", "agentbounties.app"})):
        return None, "unsafe_or_unknown_url"
    content = (title + " " + body).lower()
    for phrase in HARD_BLOCK:
        if phrase in content:
            return None, "unsafe_or_costly_request"

    # Read only natural-language tokens, never run instructions in the listing.
    tokens = set(WORDS.findall(content))
    matches = {}
    for capability, keywords in CAPABILITIES.items():
        score = 0
        for keyword, weight in keywords:
            present = keyword in content if "/" in keyword or "-" in keyword else keyword in tokens
            if present:
                score += weight
        if score:
            matches[capability] = score
    if not matches:
        return None, "out_of_scope"

    # A higher score is a ranking signal, never a promise of payment.
    match_score = min(sum(sorted(matches.values(), reverse=True)[:2]), 45)
    payout_score = {"usdc-base": 20, "x402": 7, "wallet": 1}[rail]
    escrow_claim_score = 8 if meta.get("payment_state") == "escrowed" else 0
    grade_score = GRADE.get(meta.get("payout_grade"), 0)
    value_score = min(int(amount), 20)
    score = match_score + payout_score + escrow_claim_score + grade_score + value_score

    ident = bounded_text(item.get("id"), 200)
    digest = hashlib.sha256((ident + "\n" + url + "\n" + title).encode()).hexdigest()
    return {
        "id_hash": digest, "title": title, "url": url, "source": bounded_text(meta.get("source"), 50),
        "reward_amount": amount, "reward_currency": "USDC", "payout_rail_claim": rail,
        "payment_state_claim": bounded_text(meta.get("payment_state"), 32),
        "payout_grade_claim": bounded_text(meta.get("payout_grade"), 8),
        "score": score, "capability_matches": matches,
        "verification_status": "UNVERIFIED_AGGREGATOR_LISTING",
        "execution_allowed": False,
        "contact_allowed": False,
        "required_gates": [
            "confirm_source_task_is_open_and_owner_authorized",
            "independently_validate_funding_and_actual_payout_chain",
            "verify_agent_registration_eligibility_and_zero_upfront_cost",
            "review_acceptance_criteria_before_accepting_work",
            "verify_final_receipt_and_USDC_transfer_before_counting_revenue",
        ],
    }, "candidate"


def analyze(items: object, today: dt.date) -> dict:
    if not isinstance(items, list):
        raise ValueError("items_not_list")
    if len(items) > MAX_ITEMS:
        raise ValueError("too_many_items")
    reasons: Counter[str] = Counter()
    candidates: list[dict] = []
    unique: set[str] = set()
    for item in items:
        row, reason = classify(item, today)
        reasons[reason] += 1
        if row is None or row["id_hash"] in unique:
            continue
        unique.add(row["id_hash"])
        candidates.append(row)
    candidates.sort(key=lambda x: (-x["score"], -x["reward_amount"], x["id_hash"]))
    return {
        "schema": "agent-economy.proofgate.v1",
        "scope": "read_only_public_demand_preflight",
        "financial_warning": "No sale, customer, escrow confirmation or payout verified by this artifact.",
        "observed_count": len(items),
        "candidate_count": len(candidates),
        "decision_counts": dict(sorted(reasons.items())),
        "top_candidates": candidates[:MAX_RESULTS],
    }


def corroborate(report: dict, cap: int = 6) -> None:
    for row in report["top_candidates"][:cap]:
        url = row["url"]
        if not host_allowed(url, SOURCE_HOSTS):
            row["source_probe"] = {"status": "not_attempted", "reason": "host_not_allowlisted"}
            continue
        try:
            status, _ = http_read(url, 300_000)
            row["source_probe"] = {
                "status": "reachable" if status == 200 else "not_confirmed",
                "http_status": status, "meaning": "Endpoint response only; NOT payment/funding proof."
            }
            # A dead or blocked primary endpoint cannot qualify for execution.
            if status != 200:
                row["verification_status"] = "PRIMARY_SOURCE_NOT_CONFIRMED"
        except (ValueError, URLError, TimeoutError, OSError) as exc:
            row["source_probe"] = {"status": "unavailable", "error_class": type(exc).__name__}
            row["verification_status"] = "PRIMARY_SOURCE_UNAVAILABLE"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Offline JSON Feed file, for regression tests")
    parser.add_argument("--output", default="proofgate-report.json")
    parser.add_argument("--probe", action="store_true", help="Allowlisted read-only source checks")
    args = parser.parse_args(argv)
    if args.input:
        data = Path(args.input).read_bytes()
        if len(data) > MAX_BYTES:
            raise ValueError("input_too_large")
    else:
        status, data = http_read(FEED_URL)
        if status != 200:
            raise RuntimeError("feed_unavailable_http_" + str(status))
    feed = json.loads(data)
    if not isinstance(feed, dict) or not isinstance(feed.get("items"), list):
        raise ValueError("invalid_feed")
    report = analyze(feed["items"], dt.datetime.now(dt.timezone.utc).date())
    if args.probe:
        corroborate(report)
    # Hash only the documented report body. No secrets or buyer-specific details.
    canonical = json.dumps(report, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    report["sha256"] = hashlib.sha256(canonical).hexdigest()
    report["observed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    out = Path(args.output)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"observed": report["observed_count"],
                      "candidate_count": report["candidate_count"],
                      "top": len(report["top_candidates"]),
                      "sha256": report["sha256"], "output": str(out)}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, URLError, OSError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "fail_closed", "error_class": type(exc).__name__}), file=sys.stderr)
        sys.exit(1)
