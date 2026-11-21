#!/usr/bin/env python3
"""Persistent, evidence-conservative CEO research memory for Agent Economy OS 2047.

Consumes the EXISTING public GitHub radar artifact. Never contacts prospects, runs
their content, authorizes a payment, or infers customers from GitHub metadata.
The state file belongs on a separate, restricted GitHub branch.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

SCHEMA = "agent-economy-ceo-memory/1"
REPORT_SCHEMA = "agent-economy-ceo-decision/1"
RADAR_SCHEMA = "agent-economy-public-demand-radar/2.0"
PATTERN = re.compile(r"^https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,100})/issues/([1-9][0-9]*)$")
MAX_RECORDS = 300
SHORTLIST_LIMIT = 5
STALENESS_HOURS = 4


def utc(value: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError("INVALID_TIMESTAMP") from e
    if t.tzinfo is None:
        raise ValueError("UNZONED_TIMESTAMP")
    return t.astimezone(dt.timezone.utc)


def new_state() -> dict:
    return {"schema": SCHEMA, "seen": {}, "reviews": {}}


def read_state(path: Path) -> dict:
    if not path.exists():
        return new_state()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise ValueError("INVALID_STATE_SCHEMA")
    if not isinstance(raw.get("seen"), dict) or not isinstance(raw.get("reviews"), dict):
        raise ValueError("INVALID_STATE_SHAPE")
    if len(raw["seen"]) > MAX_RECORDS:
        raise ValueError("STATE_TOO_LARGE")
    for url, value in raw["seen"].items():
        if not PATTERN.fullmatch(url) or not isinstance(value, dict):
            raise ValueError("INVALID_STATE_ENTRY")
    for url, value in raw["reviews"].items():
        if not PATTERN.fullmatch(url) or value not in ("suppressed", "needs_review"):
            raise ValueError("INVALID_REVIEW_ENTRY")
    return raw


def reconcile(radar: dict, previous: dict, now: dt.datetime) -> tuple[dict, dict]:
    if radar.get("schema_version") != RADAR_SCHEMA or not isinstance(radar.get("candidate_issues"), list):
        raise ValueError("INVALID_RADAR_SCHEMA")
    now = now.astimezone(dt.timezone.utc)
    generated = utc(radar.get("generated_at", ""))
    age = (now - generated).total_seconds()
    if age < -300 or age > STALENESS_HOURS * 3600:
        raise ValueError("RADAR_NOT_CURRENT")
    state = {"schema": SCHEMA, "seen": dict(previous["seen"]), "reviews": dict(previous["reviews"])}
    day = now.date().isoformat()
    news = []
    returning = []
    ignored = 0
    for c in radar["candidate_issues"][:100]:
        if not isinstance(c, dict):
            ignored += 1
            continue
        url = c.get("url")
        match = PATTERN.fullmatch(url) if isinstance(url, str) else None
        if not match or match.group(1).lower() == "aymanaseriai-cell":
            ignored += 1
            continue
        if c.get("buyer_intent_verified") is True or c.get("funded_opportunity_verified") is True:
            # The public radar has NO mandate to verify any of these. Fail closed.
            raise ValueError("RADAR_CLAIMS_VERIFIED_BUYER")
        tier = c.get("tier")
        if tier not in ("manual_buyer_intent_review", "research_only"):
            ignored += 1
            continue
        score = c.get("score")
        if type(score) is not int or not -100 <= score <= 100:
            ignored += 1
            continue
        if state["reviews"].get(url) == "suppressed":
            ignored += 1
            continue
        old = state["seen"].get(url)
        if old is None:
            state["seen"][url] = {
                "first_seen_day": day, "last_seen_day": day, "days_observed": 1,
                "score": score, "tier": tier,
            }
            news.append(url)
        else:
            if not isinstance(old.get("first_seen_day"), str) or not isinstance(old.get("last_seen_day"), str):
                raise ValueError("INVALID_STATE_ENTRY_DATE")
            update = dict(old)
            if update["last_seen_day"] != day:
                update["last_seen_day"] = day
                update["days_observed"] = min(1000, max(1, int(update.get("days_observed", 1))) + 1)
            update["score"] = score
            update["tier"] = tier
            state["seen"][url] = update
            returning.append(url)
    # Fail closed against large untrusted inputs and avoid storing stale research forever.
    cutoff = (now.date() - dt.timedelta(days=45)).isoformat()
    state["seen"] = {u: v for u, v in state["seen"].items() if v["last_seen_day"] >= cutoff}
    if len(state["seen"]) > MAX_RECORDS:
        ordered = sorted(state["seen"].items(), key=lambda kv: (kv[1]["last_seen_day"], kv[1]["score"], kv[0]), reverse=True)
        state["seen"] = dict(ordered[:MAX_RECORDS])
    live_urls = set(news + returning)
    ranked = [(u, v) for u, v in state["seen"].items() if u in live_urls and v["tier"] == "manual_buyer_intent_review"]
    ranked.sort(key=lambda kv: (-kv[1]["score"], kv[1]["first_seen_day"], kv[0]))
    top = [{"url": u, "heuristic_score": x["score"], "first_seen_day": x["first_seen_day"],
            "days_observed": x["days_observed"], "buyer_verified": False, "contact_allowed": False}
           for u, x in ranked[:SHORTLIST_LIMIT]]
    errors = radar.get("errors", [])
    if not isinstance(errors, list):
        raise ValueError("INVALID_RADAR_ERRORS")
    report = {
        "schema": REPORT_SCHEMA,
        "generated_at": now.isoformat(),
        "health": "partial_data" if errors else "ok",
        "new_research_candidates": len(news),
        "reappearing_candidates": len(returning),
        "suppressed_or_unusable": ignored,
        "remembered_candidates": len(state["seen"]),
        "top_manual_review": top,
        "next_action": (
            "Read the FIRST issue and its policy before any contact; check if the poster is "
            "a buyer, has explicit budget/authority, and welcomes a technical contribution."
            if top else
            "No actionable outside demand is confirmed. Seek explicit opt-in integration requests; do not pitch."
        ),
        "next_issue_url": top[0]["url"] if top else None,
        "approval_to_contact": False,
        "verified_buyers": 0,
        "verified_revenue_usd": None,
        "evidence_boundary": (
            "No third-party customer, budget, purchasing authority, independent adoption, "
            "legal contract, payment or verified revenue is derived from a search result. "
            "Research sightings are not sales. A 14-day clone count is not unique customer adoption."
        ),
    }
    return state, report


def run(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--radar", required=True, type=Path)
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--now", help="Offset-aware ISO timestamp (tests only); default current UTC")
    a = p.parse_args(argv)
    try:
        radar = json.loads(a.radar.read_text(encoding="utf-8"))
        state = read_state(a.state)
        now = utc(a.now) if a.now else dt.datetime.now(dt.timezone.utc)
        updated, report = reconcile(radar, state, now)
        a.state.parent.mkdir(parents=True, exist_ok=True)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        # Stable serialization: no hourly state churn when the candidate list is unchanged.
        content = json.dumps(updated, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if not a.state.exists() or a.state.read_text(encoding="utf-8") != content:
            a.state.write_text(content, encoding="utf-8")
        a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"CEO_MEMORY_FAIL_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"CEO memory: {report['new_research_candidates']} first sightings; "
          f"{report['remembered_candidates']} remembered; {report['health']}; "
          "no buyer or payment asserted.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
