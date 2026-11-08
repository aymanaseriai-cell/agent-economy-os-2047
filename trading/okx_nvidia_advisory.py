#!/usr/bin/env python3
"""Independent NVIDIA public-market research. NEVER used for exchange execution."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Callable

from trading.nvidia_agent_council import AGENTS, run_council
from trading.nvidia_execution_gate import GateRejected, public_snapshot, safe_nvidia_error_summary
from trading.okx_live_executor import ExecutionBlocked, choose_signal, read_report

VALID_DIRECTIONS = {"BUY", "SELL", "WAIT"}
MAX_NOTES_PER_ROLE = 2
MAX_NOTE_CHARS = 160


def _notes(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [value.replace("\n", " ").replace("\r", " ")[:MAX_NOTE_CHARS]
            for value in values[:MAX_NOTES_PER_ROLE] if isinstance(value, str)]


def advisory_only(report: dict[str, Any], api_key: str | None,
                  model: str | None = None,
                  *, council_fn: Callable[..., dict[str, Any]] = run_council) -> dict[str, Any]:
    """Only public signals; never calls OKX private endpoints or modifies orders."""
    base: dict[str, Any] = {
        "mode": "NVIDIA_ADVISORY_ONLY",
        "execution_authorized": False,
        "used_by_order_executor": False,
        "status": "NO_SIGNAL",
        "advisory": "WAIT",
        "notice": "Independent research opinions, not trade instructions or execution gates.",
    }
    try:
        signal = choose_signal(report)
    except (KeyError, TypeError, ValueError, ExecutionBlocked):
        return {**base, "status": "INVALID_QUANT_SIGNAL"}
    if signal is None:
        return base
    base["symbol"] = signal["symbol"]
    base["quant_signal"] = signal["signal"]
    if not api_key:
        return {**base, "status": "NVIDIA_NOT_CONFIGURED"}
    try:
        snapshot = public_snapshot(report, signal)
        response = council_fn(snapshot, api_key=api_key, model=model)
    except (GateRejected, Exception):
        return {**base, "status": "ADVISORY_UNAVAILABLE"}
    if not isinstance(response, dict) or response.get("mode") != "ADVISORY_ONLY" or response.get("execution_authorized") is not False:
        return {**base, "status": "INVALID_PROVIDER_RESULT"}
    votes = response.get("votes")
    if not isinstance(votes, list):
        return {**base, "status": "INVALID_PROVIDER_RESULT"}
    specialists, seen = [], set()
    for vote in votes:
        if not isinstance(vote, dict):
            continue
        role, direction, confidence = vote.get("agent"), vote.get("direction"), vote.get("confidence")
        if role not in AGENTS or role in seen or direction not in VALID_DIRECTIONS:
            continue
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            continue
        seen.add(role)
        specialists.append({
            "role": role, "direction": direction, "confidence": round(float(confidence), 3),
            "risks": _notes(vote.get("risks")), "evidence": _notes(vote.get("evidence")),
        })
    counts = {direction: sum(v["direction"] == direction for v in specialists)
              for direction in ("BUY", "SELL", "WAIT")}
    proposed = response.get("advisory")
    complete = (len(specialists) == len(AGENTS)
                and response.get("agents_expected") == len(AGENTS)
                and response.get("agents_responded") == len(AGENTS)
                and response.get("errors") == [])
    return {**base,
            "status": "COMPLETE" if complete else "PARTIAL",
            "advisory": proposed if complete and proposed in VALID_DIRECTIONS else "WAIT",
            "role_counts": counts, "roles_responded": len(specialists),
            "specialists": specialists,
            "safe_provider_diagnostics": "NONE" if complete else safe_nvidia_error_summary(response)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", default="reports/okx_six_agents.json")
    p.add_argument("--out", default="reports/nvidia_advisory.json")
    args = p.parse_args()
    try:
        report = read_report(args.report)
        result = advisory_only(report, os.environ.get("NVIDIA_API_KEY"),
                               os.environ.get("NVIDIA_MODEL"))
    except (ExecutionBlocked, OSError, ValueError, TypeError):
        result = {"mode": "NVIDIA_ADVISORY_ONLY", "status": "INVALID_OR_STALE_REPORT",
                  "execution_authorized": False, "used_by_order_executor": False,
                  "advisory": "WAIT"}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                   encoding="utf-8")
    print("NVIDIA ADVISORY ONLY: status=" + result["status"] +
          "; opinion=" + result["advisory"] +
          "; never authorizes or vetoes an OKX trade", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
