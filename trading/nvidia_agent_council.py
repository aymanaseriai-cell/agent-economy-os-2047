#!/usr/bin/env python3
"""NVIDIA NIM advisory council. Read-only; no exchange or execution capability."""
from __future__ import annotations
import argparse, json, os, re, sys, urllib.error, urllib.request
from statistics import mean
from typing import Any

API_BASE = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
AGENTS = {
    "trend": "Assess multi-timeframe trend and structure. Do not invent missing timeframes.",
    "liquidity": "Assess turnover, spread, depth, and slippage risk. Flag missing data.",
    "tape": "Assess supplied order-flow and aggressor imbalance. Do not infer unavailable trades.",
    "derivatives": "Assess supplied funding, open interest, basis, and crowding risk.",
    "news": "Assess only supplied timestamped news. If none, say no news evidence was provided.",
    "risk_critic": "Act as an adversarial risk reviewer. Identify invalidation, volatility, poor reward/risk, and reasons to WAIT.",
}
VALID_DIRECTIONS = {"BUY", "SELL", "WAIT"}

class CouncilError(RuntimeError):
    pass

def list_models(api_key: str) -> list[str]:
    request = urllib.request.Request(API_BASE + "/models",
        headers={"Authorization": "Bearer " + api_key}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        return [str(x.get("id")) for x in body.get("data", []) if isinstance(x, dict) and x.get("id")]
    except urllib.error.HTTPError as exc:
        raise CouncilError(f"NVIDIA model catalog HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise CouncilError("Could not retrieve NVIDIA model catalog") from exc

def select_model(api_key: str, preferred: str | None = None) -> str:
    models = list_models(api_key)
    if preferred and preferred in models:
        return preferred
    if DEFAULT_MODEL in models:
        return DEFAULT_MODEL
    candidates = [m for m in models if "nemotron" in m.lower()]
    if candidates:
        return candidates[0]
    raise CouncilError("NVIDIA key authenticated, but no Nemotron model is listed for this account")

def _extract_json(content: str) -> dict[str, Any]:
    value = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content.strip(), flags=re.I)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end <= start:
        raise CouncilError("Model response contained no JSON object")
    try:
        obj = json.loads(value[start:end + 1])
    except json.JSONDecodeError as exc:
        raise CouncilError("Model returned invalid JSON") from exc
    direction = str(obj.get("direction", "WAIT")).upper()
    confidence = float(obj.get("confidence", 0))
    evidence, risks = obj.get("evidence", []), obj.get("risks", [])
    if direction not in VALID_DIRECTIONS or not 0 <= confidence <= 1:
        raise CouncilError("Invalid direction or confidence")
    if not isinstance(evidence, list) or not isinstance(risks, list):
        raise CouncilError("evidence and risks must be arrays")
    return {"direction": direction, "confidence": confidence,
            "evidence": [str(x)[:300] for x in evidence[:5]],
            "risks": [str(x)[:300] for x in risks[:5]]}

def call_agent(name: str, role: str, snapshot: dict[str, Any],
               api_key: str, model: str) -> dict[str, Any]:
    system = ("You are a cautious quantitative research specialist. Analyze only supplied data; "
      "never fabricate or claim certainty. Return ONLY JSON: direction (BUY, SELL, WAIT), "
      "confidence (0..1), evidence (array), risks (array). Advisory research only. Role: " + role)
    payload = {"model": model, "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False)}],
        "temperature": 0.2, "max_tokens": 350, "stream": False}
    req = urllib.request.Request(API_BASE + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise CouncilError(f"NVIDIA inference HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise CouncilError("NVIDIA inference request failed") from exc
    try:
        result = _extract_json(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise CouncilError("NVIDIA response missing assistant content") from exc
    result["agent"] = name
    return result

def run_council(snapshot: dict[str, Any], api_key: str | None = None,
                model: str | None = None) -> dict[str, Any]:
    key = api_key or os.getenv("NVIDIA_API_KEY")
    if not key:
        raise CouncilError("NVIDIA_API_KEY is not configured")
    selected = select_model(key, model or os.getenv("NVIDIA_MODEL"))
    votes, errors = [], []
    for name, role in AGENTS.items():
        try:
            votes.append(call_agent(name, role, snapshot, key, selected))
        except CouncilError as exc:
            errors.append({"agent": name, "error": str(exc)})
    counts = {d: sum(v["direction"] == d for v in votes) for d in VALID_DIRECTIONS}
    direction = max(("BUY", "SELL"), key=lambda d: counts[d])
    aligned = [v for v in votes if v["direction"] == direction]
    advisory = "WAIT"
    if len(votes) == len(AGENTS) and len(aligned) >= 4 and mean(v["confidence"] for v in aligned) >= 0.70:
        advisory = direction
    return {"mode": "ADVISORY_ONLY", "model": selected, "agents_expected": len(AGENTS),
      "agents_responded": len(votes), "vote_counts": counts, "advisory": advisory,
      "execution_authorized": False, "votes": votes, "errors": errors,
      "notice": "Untrusted AI research only. No order was placed or authorized."}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file")
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
        print(json.dumps({"mode":"ADVISORY_ONLY","advisory":"WAIT",
          "execution_authorized":False,"error":str(exc)}))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
