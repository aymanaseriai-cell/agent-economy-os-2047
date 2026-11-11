#!/usr/bin/env python3
"""Read-only, public-evidence diagnostic of TITAN's signal decision funnel.

Never accesses OKX credentials, private endpoints, order-placement functions,
or changes the live strategy. This is NOT a backtest or profitability estimate.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path


DIRECTIONS = ("LONG", "SHORT")
MAX_EXAMPLES = 8


def audit_report(report):
    """Build a reproducible funnel from ONE completed public market report."""
    if report.get("mode") != "SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY":
        raise ValueError("Unexpected report source")
    if report.get("market_scan_complete") is not True or report.get("errors"):
        raise ValueError("Incomplete or errored public scan must not be audited as complete")
    items = report.get("results")
    if not isinstance(items, list) or not items:
        raise ValueError("No complete per-market research results")
    if report.get("markets_analyzed") != len(items):
        raise ValueError("Report result count mismatch")
    advanced_reasons, omega_reasons = Counter(), Counter()
    examples = []
    core_candidates = quant_eligible = omega_eligible = 0
    for item in items:
        if item.get("core_signal_before_advanced") not in DIRECTIONS:
            continue
        core_candidates += 1
        adv = list(item.get("advanced_veto_reasons") or [])
        omega = list(item.get("omega_veto_reasons") or [])
        advanced_reasons.update(adv)
        # Omega may have abstained because advanced already set WAIT. In that
        # case its apparent lack of veto DOES NOT mean Omega would have passed.
        quant_pass = (not adv and item.get("advanced_confirmations", 0) >= 1
                      and not item.get("derivatives_data_warnings"))
        if quant_pass:
            quant_eligible += 1
            omega_reasons.update(omega)
        else:
            # Omega evidence for a previous-stage rejection is not considered
            # a valid independent pass.
            omega = ["NOT_EVALUATED_ON_REJECTED_DIRECTION"]
        final_pass = (
            quant_pass
            and item.get("omega_system_count") == 10
            and not omega
            and item.get("omega_rank_score", 0) > 0
            and item.get("signal") in DIRECTIONS
        )
        if final_pass:
            omega_eligible += 1
        evidence = ((item.get("omega_systems") or [{}])[0]
                    .get("evidence") or {})
        examples.append({
            "symbol": str(item.get("symbol", "")),
            "direction": item["core_signal_before_advanced"],
            "quant_confirmations": int(item.get("advanced_confirmations") or 0),
            "advanced_vetoes": adv,
            "omega_vetoes": omega,
            "omega_null_model_net_bp": (
                evidence.get("net_expectation_bp_null_model") if quant_pass
                else None
            ),
            "accepted_for_research": final_pass,
        })
    reported = report.get("actionable_research_labels")
    if reported != sum(item.get("signal") in DIRECTIONS for item in items):
        raise ValueError("Inconsistent final signal count")
    if omega_eligible != reported:
        raise ValueError("Accepted signal accounting mismatch")
    return {
        "utc_timestamp": str(report.get("utc_timestamp", "")),
        "20x_crypto_contracts_screened": int(report.get("markets_screened_for_liquidity") or 0),
        "liquid_contracts_analyzed": len(items),
        "core_candidates": core_candidates,
        "passed_independent_quant": quant_eligible,
        "passed_omega_and_research": omega_eligible,
        "advanced_veto_counts": dict(sorted(advanced_reasons.items())),
        "omega_veto_counts_after_quant": dict(sorted(omega_reasons.items())),
        "candidate_evidence": sorted(
            examples, key=lambda x: (not x["accepted_for_research"], x["symbol"])
        )[:MAX_EXAMPLES],
        "no_orders_placed_by_this_audit": True,
        "interpretation": (
            "Research diagnostics only; no historical out-of-sample test, "
            "calibrated success probability, or proven positive edge. "
            "Omega rejection is counted only when independent quant passed."
        ),
    }


def markdown_summary(stats):
    lines = [
        "### TITAN Ω: public signal-decision audit (NO ORDERS)",
        "",
        f"- Report time (UTC): `{stats['utc_timestamp']}`",
        f"- Screened 20x cryptocurrency contracts: **{stats['20x_crypto_contracts_screened']}**",
        f"- Deep analyzed after liquidity filters: **{stats['liquid_contracts_analyzed']}**",
        f"- Initial core directional candidates: **{stats['core_candidates']}**",
        f"- Passed independent quant gate: **{stats['passed_independent_quant']}**",
        f"- Passed Omega and all research gates: **{stats['passed_omega_and_research']}**",
        "",
        "**Independent-quant rejection counts:** "
        + json.dumps(stats["advanced_veto_counts"], ensure_ascii=True),
        "",
        "**Omega rejection counts (quant-passing only):** "
        + json.dumps(stats["omega_veto_counts_after_quant"], ensure_ascii=True),
        "",
        "| Core candidate | Direction | Quant confirmations | Advanced veto | Omega veto | Null-model net bp |",
        "|---|---|---:|---|---|---:|",
    ]
    for item in stats["candidate_evidence"]:
        symbol = "".join(ch for ch in item["symbol"] if ch.isalnum() or ch in "-_")
        adv = ", ".join(item["advanced_vetoes"]) or "none"
        omega = ", ".join(item["omega_vetoes"]) or "none"
        bp = item["omega_null_model_net_bp"]
        value = f"{float(bp):.1f}" if bp is not None else "N/A"
        lines.append(
            f"| {symbol} | {item['direction']} | {item['quant_confirmations']} | "
            f"{adv} | {omega} | {value} |"
        )
    lines += [
        "",
        "*Diagnostic only. Research estimates are not probabilities, backtests, "
        "profit guarantees, or instructions to remove trading protections.*",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary", help="Append public-only summary to GitHub step summary")
    args = parser.parse_args()
    path = Path(args.report)
    if not path.is_file():
        print("TITAN AUDIT: no completed public research file; nothing to audit")
        return 0
    try:
        audit = audit_report(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("TITAN AUDIT: unavailable/incomplete evidence, no score inferred:", exc)
        return 2
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    if args.summary:
        with Path(args.summary).open("a", encoding="utf-8") as stream:
            stream.write(markdown_summary(audit))
    print("TITAN AUDIT: screened=", audit["20x_crypto_contracts_screened"],
          "analyzed=", audit["liquid_contracts_analyzed"],
          "core_candidates=", audit["core_candidates"],
          "quant_pass=", audit["passed_independent_quant"],
          "fully_accepted=", audit["passed_omega_and_research"],
          "NO ORDERS")
    print("TITAN AUDIT ADVANCED VETOES:",
          json.dumps(audit["advanced_veto_counts"], sort_keys=True))
    print("TITAN AUDIT OMEGA VETOES:",
          json.dumps(audit["omega_veto_counts_after_quant"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
