#!/usr/bin/env python3
"""NVIDIA NIM advisory council. This module is intentionally read-only.

It accepts a sanitized market snapshot and returns advisory votes. It has no
OKX credentials, exchange client, order-placement code, or execution hooks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from statistics import mean
from typing import Any

API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
AGENTS = {
    "trend": "Assess multi-timeframe trend and market structure. Do not invent missing timeframes.",
    "liquidity": "Assess liquidity, turnover, spread, depth, and slippage risk. Flag thin or missing data.",
    "tape": "Assess order-flow, aggressor imbalance, and volume confirmation. Do not infer unavailable trades.",
    "derivatives": "Assess funding, open interest, basis, and liquidation/crowding risk. Flag missing fields.",
    "news": "Assess only supplied event/news context and its timestamp. If none is supplied, state that no news evidence was provided.",
    "risk_critic": "Act as an adversarial risk reviewer. Look for invalidation, volatility, poor reward/risk, and reasons to WAIT.",
}
VALID_DIRECTIONS = {"BUY", "SELL", "WAIT"}


class CouncilError(RuntimeError):
    pass


def _extract_json(content: str) -> dict[str, Any]:
    text = content.strip()
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise CouncilError("Model response did not contain a JSON object")
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise CouncilError("Model returned invalid JSON") from exc
    if not isinstance(obj, dict):
        raise CouncilError("Model response must be a JSON object")
    direction = str(obj.get("direction", "WAIT")).upper()
    if direction not in VALID_DIRECTIONS:
        raise CouncilError("Invalid direction")
    try:
        confidence = float(obj.get("confidence", 0))
    except (TypeError, ValueError) as exc:
        raise CouncilError("Invalid confidence") from exc
    if not 0 <= confidence <= 1:
        raise CouncilError("Confidence must be between 0 and 1")
    evidence = obj.get("evidence", [])
    risks = obj.get("risks", [])
    if not isinstance(evidence, list) or not isinstance(risks, list):
        raise CouncilError("evidence and risks must be arrays")
    return {
        "direction": direction,
        "confidence": confidence,
        "evidence": [str(x)[:300] for x in evidence[:5]],
        "risks": [str(x)[:300] for x in risks[:5]],
    }


def call_agent(name: str, instruction: str, snapshot: dict[str, Any],
               api_key: str, model: str, timeout: int = 35) -> dict[str, Any]:
    system = (
        "You are one specialist in a cautious quantitative research council. "
        "Analyze only the supplied snapshot. Never fabricate data or claim certainty. "
        "Return ONLY JSON with keys direction (BUY, SELL, or WAIT), confidence "
        "(0..1), evidence (array of short strings), risks (array of short strings). "
        "This is advisory research, not an instruction to trade."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system + " Role: " + instruction},
            {"role": "user", "content": json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False)},
        ],
        "temperature": 0.1,
        "max_tokens": 350,
        "stream": False,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise CouncilError(f"NVIDIA API HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CouncilError("NVIDIA API request failed") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CouncilError("NVIDIA API returned an unreadable response") from exc
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise CouncilError("NVIDIA API response missing assistant content") from exc
    result = _extract_json(content)
    result["agent"] = name
    return result


def run_council(snapshot: dict[str, Any], api_key: str | None = None,
                model: str | None = None) -> dict[str, Any]:
    key = api_key or os.getenv("NVIDIA_API_KEY")
    if not key:
        raise CouncilError("NVIDIA_API_KEY is not configured")
    selected_model = model or os.getenv("NVIDIA_MODEL", DEFAULT_MODEL)
    votes: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    # Sequential calls avoid burst rate-limit pressure on hosted NIM.
    for name, instruction in AGENTS.items():
        try:
            votes.append(call_agent(name, instruction, snapshot, key, selected_model))
        except CouncilError as exc:
            errors.append({"agent": name, "error": str(exc)})
    counts = {d: sum(v["direction"] == d for v in votes) for d in VALID_DIRECTIONS}
    winner = max(("BUY", "SELL"), key=lambda d: counts[d])
    matching = [v for v in votes if v["direction"] == winner]
    # Fail closed: require all six valid votes, >=4 aligned directional votes,
    # and average confidence >=0.70. This is still NOT a trade authorization.
    advisory = "WAIT"
    if len(votes) == len(AGENTS) and len(matching) >= 4 and mean(v["confidence"] for v in matching) >= 0.70:
        advisory = winner
    return {
        "mode": "ADVISORY_ONLY",
        "model": selected_model,
        "agents_expected": len(AGENTS),
        "agents_responded": len(votes),
        "vote_counts": counts,
        "advisory": advisory,
        "execution_authorized": False,
        "votes": votes,
        "errors": errors,
        "notice": "AI output is untrusted research. No order was placed or authorized.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", help="JSON market snapshot; defaults to stdin")
    args = parser.parse_args()
    try:
        raw = open(args.input_file, encoding="utf-8").read() if args.input_file else sys.stdin.read()
        snapshot = json.loads(raw)
        if not isinstance(snapshot, dict):
            raise CouncilError("Input must be a JSON object")
        result = run_council(snapshot)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["agents_responded"] == len(AGENTS) else 2
    except (OSError, json.JSONDecodeError, CouncilError) as exc:
        print(json.dumps({"mode": "ADVISORY_ONLY", "advisory": "WAIT",
                          "execution_authorized": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
