#!/usr/bin/env python3
"""Exercise exact review-only safe-rollback verdict in isolated PostgreSQL 16.

No Supabase/production credentials, cron, provider fetch, payments, or writes.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "infra/supabase/factory_watchdog_freeze_replay_20261123.sql"
FUNCTION = re.compile(
    r"(CREATE OR REPLACE FUNCTION executive_nexus\.factory_watchdog_verdict\("
    r"[\s\S]*?\$function\$;)"
)


def extracted_function() -> str:
    matches = FUNCTION.findall(SOURCE.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise ValueError("FREEZE_ROLLBACK_FUNCTION_SOURCE_MISSING_OR_AMBIGUOUS")
    if "ELSE 'RUN_STATUS_UNCERTAIN_NO_REPLAY'" not in matches[0]:
        raise ValueError("FREEZE_ROLLBACK_MUST_FAIL_CLOSED")
    return matches[0]


def cases() -> list[tuple[str, str, str, str]]:
    # tuple: label, last_start, last_status, expected; all are SQL literals
    return [
        ("successful_due", "v_due", "'succeeded'", "HEALTHY"),
        ("running_due", "v_due", "'running'", "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("queued_due", "v_due", "'queued'", "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("failed_due", "v_due", "'failed'", "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("missing_status", "v_due", "NULL", "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("no_run", "NULL::timestamptz", "NULL", "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("old_success", "v_due - interval '20 minutes'", "'succeeded'", "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("future_success", "v_now + interval '3 minutes'", "'succeeded'", "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
    ]


def test_sql() -> str:
    assertions = []
    for label, last, status, expected in cases():
        assertions.append(
            "v_actual := executive_nexus.factory_watchdog_verdict("
            f"true,true,v_due,v_first,{last},{status},v_now);\n"
            f"IF v_actual IS DISTINCT FROM '{expected}' THEN "
            f"RAISE EXCEPTION 'FREEZE_CASE_{label}: expected {expected}, got %', v_actual; "
            "END IF;\n"
            f"RAISE NOTICE 'PASS freeze case: {label}';"
        )
    variants = [
        ("human_pause", "false,true,v_due,v_first,v_due,'failed',v_now", "PAUSED_NO_OVERRIDE"),
        ("config_drift", "true,false,v_due,v_first,v_due,'failed',v_now", "CONFIG_DRIFT_BLOCKED"),
        ("warmup", "true,true,v_due,v_due + interval '1 minute',NULL,NULL,v_now", "WARMUP_NOT_DUE"),
        ("grace", "true,true,v_due,v_first,NULL,NULL,v_due + interval '1 minute'", "WAIT_EXPECTED_RUN"),
        ("missing_due", "true,true,NULL,v_first,v_due,'succeeded',v_now", "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("missing_clock", "true,true,v_due,v_first,v_due,'succeeded',NULL", "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
    ]
    for label, args, expected in variants:
        assertions.append(
            f"v_actual := executive_nexus.factory_watchdog_verdict({args});\n"
            f"IF v_actual IS DISTINCT FROM '{expected}' THEN "
            f"RAISE EXCEPTION 'FREEZE_CASE_{label}: expected {expected}, got %', v_actual; "
            "END IF;\n"
            f"RAISE NOTICE 'PASS freeze case: {label}';"
        )
    return (
        "BEGIN;\nCREATE SCHEMA executive_nexus;\n" + extracted_function()
        + "\nDO $tests$\nDECLARE\n"
        + "v_due timestamptz := '2026-11-23 14:19:00+00';\n"
        + "v_first timestamptz := '2026-11-21 00:00:00+00';\n"
        + "v_now timestamptz := '2026-11-23 14:25:00+00';\n"
        + "v_actual text;\nBEGIN\n" + "\n".join(assertions)
        + "\nEND $tests$;\nROLLBACK;\n"
    )


def main() -> int:
    if not os.getenv("PGHOST") or not os.getenv("PGDATABASE"):
        raise ValueError("ISOLATED_POSTGRES_TEST_CONNECTION_REQUIRED")
    r = subprocess.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-q"],
                       input=test_sql(), capture_output=True, text=True,
                       check=False, timeout=45)
    if r.returncode:
        print(r.stderr[-5000:], file=sys.stderr)
        return r.returncode
    print(r.stderr.strip())
    print("POSTGRES_WATCHDOG_FREEZE: 14/14 exact-source cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
