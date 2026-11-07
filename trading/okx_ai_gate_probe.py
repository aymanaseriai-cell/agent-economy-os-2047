#!/usr/bin/env python3
"""Read-only OKX + NVIDIA gate smoke check with public market data only."""
from __future__ import annotations
import argparse, os

from trading.okx_live_executor import read_report, choose_signal
from trading.nvidia_execution_gate import GateRejected, require_nvidia_veto_pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="reports/okx_six_agents.json")
    args = parser.parse_args()
    try:
        report = read_report(args.report)
        signal = choose_signal(report)
        if signal is None:
            print("AI GATE READ-ONLY: no qualified quant signal; NO ORDERS")
            return 0
        print("AI GATE READ-ONLY: qualified public market data; checking NVIDIA veto")
        try:
            result = require_nvidia_veto_pass(
                report, signal, os.environ.get("NVIDIA_API_KEY"),
                os.environ.get("NVIDIA_MODEL") or None,
            )
        except GateRejected as exc:
            print("AI GATE READ-ONLY: VETO =", str(exc), "; NO ORDERS")
            return 0
        print("AI GATE READ-ONLY: NVIDIA did not veto", result["direction"],
              "on this snapshot; NO ORDERS")
        return 0
    except Exception:
        print("AI GATE READ-ONLY: report or probe failure; NO ORDERS")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
