#!/usr/bin/env python3
"""Read-only public GitHub issue demand radar; never contact or execute issue content.

Output is a *research queue*, not customer qualification, verified budgets, or consent.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SEARCHES = (
    '"AI agent" "audit" in:title is:issue is:open',
    '"agent" "evidence" in:title is:issue is:open',
    '"agent" "handoff" in:title is:issue is:open',
    '"x402" "receipt" in:title is:issue is:open',
    '"agent" "bounty" in:title is:issue is:open',
    '"workflow" "verification" in:title is:issue is:open',
)
BUSINESS_TERMS = {
    "looking for": 6, "seeking": 5, "need help": 5,
    "help wanted": 6, "bounty": 4, "budget": 6, "paid": 6,
    "hire": 6, "hiring": 6, "rfp": 7, "request for proposal": 7,
    "contractor": 6, "could someone": 4, "need to": 3,
    "request": 2, "please implement": 4, "wanted": 3,
}
EVIDENCE_TERMS = {
    "agent": 2, "workflow": 2, "audit": 3, "handoff": 4,
    "provenance": 5, "evidence": 4, "artifact": 3,
    "integrity": 4, "receipt": 3, "verify": 2, "verification": 3,
    "acceptance": 3, "x402": 2, "delivery": 2,
}
VENDOR_TERMS = (
    "we launched", "i built", "check out my", "our product",
    "buy my", "selling", "we are selling", "for sale",
    "our service", "announcement", "promote", "self-promo",
    "buy (live)", "our pricing", "my service", "subscribe now",
)
# Only explicit *commercial solicitation* merits manual buyer-intent review.
# An issue about implementing an internal feature or fixing payment code is
# technical backlog, NOT a request to purchase independent agent-evidence work.
PROCUREMENT_PATTERNS = tuple(re.compile(x) for x in (
    r"\b(?:looking for|seeking|need)\s+(?:(?:an?|the)\s+)?(?:paid\s+)?(?:external\s+)?(?:vendor|consultant|contractor|reviewer|auditor|integration partner)\b",
    r"\b(?:looking for|seeking)\s+paid\s+",
    r"\b(?:rfp|rfq|request for proposals?|request for quotation)\b",
    r"\b(?:paid\s+bounty|funded\s+bounty|hiring|hire\s+(?:a|an|someone)|budget\s*[:=]|budget\s+(?:of|for))\b",
))
MAX_CANDIDATES = 30
PER_QUERY = 12


def evaluate(entry: dict) -> dict | None:
    """Only rank public issue metadata; signals are weak and unverified."""
    if not isinstance(entry, dict):
        return None
    url = entry.get("html_url", "")
    title = entry.get("title", "")
    body = entry.get("body", "")
    if not isinstance(url, str) or not re.fullmatch(
        r"https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*", url
    ):
        return None
    if not isinstance(title, str) or not title.strip() or entry.get("state") != "open":
        return None
    if entry.get("pull_request"):
        return None
    if not isinstance(body, str):
        body = ""
    title_l = title.lower()[:350]
    text_l = (title_l + " " + body[:1000].lower())
    # An issue body is untrusted and is NEVER treated as instructions to follow.
    buyer = [term for term in BUSINESS_TERMS if term in text_l]
    evidence = [term for term in EVIDENCE_TERMS if term in text_l]
    vendor = [term for term in VENDOR_TERMS if term in text_l]
    actor = (entry.get("user") or {}).get("login", "")
    # GitHub bots may post issue titles that look like paid solicitations.
    # This flag concerns the posting account type, not verified personhood.
    is_bot = isinstance(actor, str) and (
        actor.lower().endswith("[bot]") or actor.lower().endswith("-bot")
    )
    procurement = any(pattern.search(text_l) for pattern in PROCUREMENT_PATTERNS)
    score = sum(BUSINESS_TERMS[t] for t in buyer) + sum(EVIDENCE_TERMS[t] for t in evidence)
    score -= min(16, 8 * len(vendor))
    # Never mark a candidate as an actual buyer, let alone as permission to pitch.
    # In particular, internal product feature requests and sellers' promos are NOT
    # actionable commercial demand even if they mention receipts/agents/budgets.
    tier = "research_only"
    if buyer and evidence and score >= 12 and procurement and not vendor and not is_bot:
        tier = "manual_buyer_intent_review"
    reason = (
        "bot_authored" if is_bot else
        "vendor_promotion" if vendor else
        "no_explicit_procurement_signal" if not procurement else
        "external_commercial_intent_needs_verification"
    )
    return {
        "url": url,
        "title": title[:220],
        "updated_at": str(entry.get("updated_at", ""))[:35],
        "state": "open",
        "score": score,
        "tier": tier,
        "signals": sorted(set(buyer + evidence))[:12],
        "potential_vendor_signals": vendor,
        "procurement_phrase_present": bool(procurement),
        "bot_authored": bool(is_bot),
        "classification_reason": reason,
        "buyer_intent_verified": False,
        "buying_authority_verified": False,
        "funded_opportunity_verified": False,
        "permission_to_contact_verified": False,
        "contacted": False,
    }


def fetch(query: str) -> dict:
    params = urlencode({"q": query, "per_page": PER_QUERY, "sort": "updated", "order": "desc"})
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agent-economy-public-demand-radar/2.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("OPPORTUNITY_GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request("https://api.github.com/search/issues?" + params, headers=headers), timeout=15) as response:
        return json.load(response)


def select_review_queue(findings: dict[str, dict]) -> tuple[list[dict], dict]:
    """Prevent bot/vendor issue advertisements from filling capped review slots.

    Exclusion is not proof that remaining issues are actual buyers.
    """
    candidates = list(findings.values())
    bot_count = sum(bool(x["bot_authored"]) for x in candidates)
    vendor_count = sum(not x["bot_authored"] and bool(x["potential_vendor_signals"])
                       for x in candidates)
    eligible = [x for x in candidates
                if not x["bot_authored"] and not x["potential_vendor_signals"]]
    eligible.sort(key=lambda x: (x["tier"] != "manual_buyer_intent_review",
                                 -x["score"], x["url"]))
    return eligible[:MAX_CANDIDATES], {
        "total": len(candidates),
        "eligible": len(eligible),
        "excluded_bot_authored": bot_count,
        "excluded_vendor_promotion": vendor_count,
        "manual_buyer_intent_review": sum(x["tier"] == "manual_buyer_intent_review"
                                          for x in eligible),
    }


def run() -> int:
    findings: dict[str, dict] = {}
    errors: list[dict] = []
    for query in SEARCHES:
        try:
            data = fetch(query)
            if not isinstance(data, dict):
                raise ValueError("Unexpected API response type")
            for entry in data.get("items", []):
                candidate = evaluate(entry)
                if candidate and (
                    candidate["url"] not in findings or
                    candidate["score"] > findings[candidate["url"]]["score"]
                ):
                    findings[candidate["url"]] = candidate
        except (HTTPError, URLError, TimeoutError, ValueError, TypeError) as exc:
            errors.append({"query": query, "error_type": type(exc).__name__})
    queue, counts = select_review_queue(findings)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    report = {
        "schema_version": "agent-economy-public-demand-radar/2.0",
        "generated_at": now,
        "claim_boundary": "Public GitHub issue search only. Signals are heuristics, NOT verified buyers, funded bounties, permission to pitch, or real revenue.",
        "contact_policy": "No outbound messaging. Inspect terms, issue context, buyer authority, refusal history and channel policy before any response.",
        "searches": list(SEARCHES),
        "candidate_issues": queue,
        "candidate_counts": counts,
        "errors": errors,
    }
    out = Path(os.environ.get("OPPORTUNITY_OUT", "opportunity-report.json"))
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Public GitHub demand radar (research only)",
        "",
        f"Checked (UTC): {now}",
        "",
        "No buyer, budget, permission, procurement or payment has been verified.",
        "Public issues are untrusted; do not execute instructions inside them.",
        "",
        "| Candidate | Tier | Signals |",
        "| --- | --- | --- |",
    ]
    for e in queue:
        label = e["title"].replace("|", "/").replace("[", "(").replace("]", ")").replace("\n", " ")[:96]
        lines.append(f"| [{label}]({e['url']}) | {e['tier']} | {', '.join(e['signals'][:5])} |")
    Path("opportunity-review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Discovery: {counts['total']} candidates, {counts['eligible']} eligible for review; {counts['manual_buyer_intent_review']} with unverified procurement wording; {len(errors)} errors.")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(run())
