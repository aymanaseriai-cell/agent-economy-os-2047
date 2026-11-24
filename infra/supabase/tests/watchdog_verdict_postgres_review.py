#!/usr/bin/env python3
"""Execute the exact review-only watchdog verdict SQL in an isolated PostgreSQL.

No Supabase connection, no production writes, no cron, no money, and no
assumption that passing SQL tests constitutes independent release approval.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "infra/supabase/factory_cron_watchdog_20261121.sql"
FUNCTION_PATTERN = re.compile(
    r"(CREATE OR REPLACE FUNCTION executive_nexus\.factory_watchdog_verdict\("
    r"[\s\S]*?\$function\$;)"
)


def extracted_function() -> str:
    raw = SOURCE.read_text(encoding="utf-8")
    hits = FUNCTION_PATTERN.findall(raw)
    if len(hits) != 1:
        raise ValueError("EXACT_WATCHDOG_VERDICT_SOURCE_NOT_FOUND")
    return hits[0]


def constraint_migration_sql() -> str:
    """Rehearse the exact constraint DDL against the previous verdict domain.

    Synthetic historical rows cover all previously allowed statuses; this is
    not a copy of production data or a full production migration rehearsal.
    """
    raw = SOURCE.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(ALTER TABLE executive_nexus\.factory_cron_watchdog_checks\s+"
        r"DROP CONSTRAINT IF EXISTS factory_cron_watchdog_checks_verdict_check;\s*"
        r"ALTER TABLE executive_nexus\.factory_cron_watchdog_checks\s+"
        r"ADD CONSTRAINT factory_cron_watchdog_checks_verdict_check CHECK\(verdict IN \([\s\S]*?\)\);)"
    )
    hits = pattern.findall(raw)
    if len(hits) != 1:
        raise ValueError("EXACT_VERDICT_CONSTRAINT_MIGRATION_NOT_FOUND")
    return """
CREATE TABLE executive_nexus.factory_cron_watchdog_checks (
    verdict text NOT NULL CONSTRAINT factory_cron_watchdog_checks_verdict_check
    CHECK (verdict IN (
      'EVALUATING','HEALTHY','PAUSED_NO_OVERRIDE','CONFIG_DRIFT_BLOCKED',
      'WARMUP_NOT_DUE','WAIT_EXPECTED_RUN','READONLY_REPLAY_SUCCEEDED',
      'READONLY_REPLAY_FAILED'))
);
INSERT INTO executive_nexus.factory_cron_watchdog_checks VALUES
 ('EVALUATING'),('HEALTHY'),('PAUSED_NO_OVERRIDE'),('CONFIG_DRIFT_BLOCKED'),
 ('WARMUP_NOT_DUE'),('WAIT_EXPECTED_RUN'),('READONLY_REPLAY_SUCCEEDED'),
 ('READONLY_REPLAY_FAILED');
""" + hits[0] + """
DO $migration_test$
BEGIN
  IF (SELECT count(*) FROM executive_nexus.factory_cron_watchdog_checks) <> 8 THEN
    RAISE EXCEPTION 'VERDICT_MIGRATION_HISTORICAL_ROWS_LOST';
  END IF;
  INSERT INTO executive_nexus.factory_cron_watchdog_checks
    VALUES ('RUN_STATUS_UNCERTAIN_NO_REPLAY');
  BEGIN
    INSERT INTO executive_nexus.factory_cron_watchdog_checks VALUES ('REPLAY_ELIGIBLE');
    RAISE EXCEPTION 'VERDICT_MIGRATION_ACCEPTED_INTERNAL_DECISION';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  BEGIN
    INSERT INTO executive_nexus.factory_cron_watchdog_checks VALUES ('UNKNOWN');
    RAISE EXCEPTION 'VERDICT_MIGRATION_ACCEPTED_UNKNOWN';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  IF (SELECT count(*) FROM executive_nexus.factory_cron_watchdog_checks) <> 9 THEN
    RAISE EXCEPTION 'VERDICT_MIGRATION_UNEXPECTED_ROW_COUNT';
  END IF;
  RAISE NOTICE 'PASS exact constraint migration: 8 historical statuses, new fail-closed status, two rejected invalid statuses';
END $migration_test$;
"""


def test_sql() -> str:
    due = "v_due"
    first = "v_first"
    now = "v_now"
    no_time = "NULL::timestamptz"
    cases = [
        ("healthy-exact", "TRUE", "TRUE", due, first, due, "'succeeded'", now, "HEALTHY"),
        ("healthy-later", "TRUE", "TRUE", due, first, "v_due + interval '2 minutes'", "'succeeded'", now, "HEALTHY"),
        ("failed-replay-eligible", "TRUE", "TRUE", due, first, due, "'failed'", now, "REPLAY_ELIGIBLE"),
        ("never-ran-eligible", "TRUE", "TRUE", due, first, no_time, "NULL", now, "REPLAY_ELIGIBLE"),
        ("old-success-not-current", "TRUE", "TRUE", due, first, "v_due - interval '15 minutes'", "'succeeded'", now, "REPLAY_ELIGIBLE"),
        ("future-success-untrusted", "TRUE", "TRUE", due, first, "v_now + interval '1 minute'", "'succeeded'", now, "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("future-failure-untrusted", "TRUE", "TRUE", due, first, "v_now + interval '1 minute'", "'failed'", now, "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("running-after-due", "TRUE", "TRUE", due, first, due, "'running'", now, "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("running-before-due", "TRUE", "TRUE", due, first, "v_due - interval '1 minute'", "'running'", now, "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("queued-missing-time", "TRUE", "TRUE", due, first, no_time, "'queued'", now, "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("success-missing-time", "TRUE", "TRUE", due, first, no_time, "'succeeded'", now, "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("timestamp-missing-status", "TRUE", "TRUE", due, first, due, "NULL", now, "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("null-due", "TRUE", "TRUE", no_time, first, due, "'succeeded'", now, "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("null-clock", "TRUE", "TRUE", due, first, due, "'succeeded'", no_time, "RUN_STATUS_UNCERTAIN_NO_REPLAY"),
        ("human-paused", "FALSE", "TRUE", due, first, due, "'running'", now, "PAUSED_NO_OVERRIDE"),
        ("config-drift", "TRUE", "FALSE", due, first, due, "'succeeded'", now, "CONFIG_DRIFT_BLOCKED"),
        ("first-run-warmup", "TRUE", "TRUE", due, "v_due + interval '1 minute'", no_time, "NULL", now, "WARMUP_NOT_DUE"),
        ("before-grace", "TRUE", "TRUE", due, first, no_time, "NULL", "v_due + interval '1 minute'", "WAIT_EXPECTED_RUN"),
    ]
    statements = []
    for label, enabled, config, a_due, a_first, last, status, a_now, expected in cases:
        statements.append(
            "v_actual := executive_nexus.factory_watchdog_verdict("
            f"{enabled},{config},{a_due},{a_first},{last},{status},{a_now});\n"
            f"IF v_actual IS DISTINCT FROM '{expected}' THEN "
            f"RAISE EXCEPTION 'WATCHDOG_CASE_{label}: expected {expected}, got %', v_actual; "
            "END IF;\n"
            f"RAISE NOTICE 'PASS watchdog case: {label}';"
        )
    return (
        "BEGIN;\nCREATE SCHEMA executive_nexus;\n"
        + constraint_migration_sql()
        + extracted_function()
        + "\nDO $tests$\nDECLARE\n"
        + "  v_due timestamptz := '2026-11-22 05:19:00+00';\n"
        + "  v_first timestamptz := '2026-11-22 04:00:00+00';\n"
        + "  v_now timestamptz := '2026-11-22 05:25:00+00';\n"
        + "  v_actual text;\n"
        + "BEGIN\n"
        + "\n".join(statements)
        + "\nEND $tests$;\nROLLBACK;\n"
    )


def main() -> int:
    if not os.environ.get("PGHOST") or not os.environ.get("PGDATABASE"):
        raise ValueError("ISOLATED_POSTGRES_TEST_CONNECTION_REQUIRED")
    command = ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-q"]
    result = subprocess.run(command, input=test_sql(), text=True,
                            capture_output=True, check=False, timeout=45)
    if result.returncode:
        print(result.stderr[-5000:], file=sys.stderr)
        return result.returncode
    print(result.stderr.strip())
    print("POSTGRES_WATCHDOG_VERDICT: 18/18 exact-source adversarial cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
