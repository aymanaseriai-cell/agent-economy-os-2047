#!/usr/bin/env python3
"""Review-only PostgreSQL 17 migration rehearsal; synthetic rows, no live cron."""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "infra/supabase"
MIGRATION = BASE / "factory_cron_watchdog_20261121.sql"
FREEZE = BASE / "factory_watchdog_freeze_replay_20261123.sql"

# Exact legacy verdict allowlist observed in production on 2026-11-24.
# Other columns and constraints mirror the review source; no live rows copied.
SETUP = """
BEGIN;
CREATE SCHEMA executive_nexus;
CREATE SCHEMA cron;
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE TABLE executive_nexus.factory_cron_watchdog_checks (
 slot timestamptz NOT NULL, jobid bigint NOT NULL, jobname text NOT NULL,
 expected_run_at timestamptz NOT NULL, observed_latest_run_at timestamptz,
 observed_cron_status text, verdict text NOT NULL,
 retry_attempts integer NOT NULL DEFAULT 0 CHECK(retry_attempts BETWEEN 0 AND 1),
 internal_replay_result jsonb NOT NULL DEFAULT '{}'::jsonb,
 checked_at timestamptz NOT NULL DEFAULT now(),
 execution_origin text NOT NULL DEFAULT 'UNVERIFIED'
 CHECK(execution_origin IN ('USER_REQUEST','UNVERIFIED','INDEPENDENT_SCHEDULED_VERIFIED')),
 PRIMARY KEY(slot,jobid),
 CONSTRAINT no_external_actions_watchdog CHECK(jsonb_typeof(internal_replay_result)='object'),
 CONSTRAINT factory_cron_watchdog_checks_verdict_check CHECK(verdict IN (
 'EVALUATING','HEALTHY','PAUSED_NO_OVERRIDE','CONFIG_DRIFT_BLOCKED','WARMUP_NOT_DUE',
 'WAIT_EXPECTED_RUN','READONLY_REPLAY_SUCCEEDED','READONLY_REPLAY_FAILED'))
);
CREATE TABLE cron.job(jobid bigint PRIMARY KEY, active bool, jobname text, schedule text, command text);
CREATE TABLE cron.job_run_details(jobid bigint, start_time timestamptz, status text);
CREATE TABLE executive_nexus.factory_review_cycles(observed_at timestamptz);
CREATE TABLE executive_nexus.market_failover_checks(checked_at timestamptz);
CREATE TABLE executive_nexus.test_replays(jobid bigint);
CREATE FUNCTION executive_nexus.run_factory_review_cycle() RETURNS jsonb LANGUAGE plpgsql AS
$$BEGIN INSERT INTO executive_nexus.test_replays VALUES (26); RETURN '{}'::jsonb; END$$;
CREATE FUNCTION executive_nexus.run_market_failover_check() RETURNS jsonb LANGUAGE plpgsql AS
$$BEGIN INSERT INTO executive_nexus.test_replays VALUES (27); RETURN '{}'::jsonb; END$$;
INSERT INTO executive_nexus.factory_cron_watchdog_checks(slot,jobid,jobname,expected_run_at,verdict)
SELECT '2026-11-23 08:00+00',i,'fixture','2026-11-23 08:19+00',v
FROM unnest(ARRAY['EVALUATING','HEALTHY','PAUSED_NO_OVERRIDE','CONFIG_DRIFT_BLOCKED',
 'WARMUP_NOT_DUE','WAIT_EXPECTED_RUN','READONLY_REPLAY_SUCCEEDED','READONLY_REPLAY_FAILED'])
WITH ORDINALITY AS a(v,i);
CREATE TEMP TABLE original_rows AS SELECT * FROM executive_nexus.factory_cron_watchdog_checks;
DO $$BEGIN
 BEGIN
 INSERT INTO executive_nexus.factory_cron_watchdog_checks(slot,jobid,jobname,expected_run_at,verdict)
 VALUES ('2026-11-23 08:00+00',99,'fixture','2026-11-23 08:19+00','RUN_STATUS_UNCERTAIN_NO_REPLAY');
 RAISE EXCEPTION 'legacy constraint unexpectedly accepted new verdict';
 EXCEPTION WHEN check_violation THEN NULL; END;
 RAISE NOTICE 'PASS legacy rejection';
END$$;
"""
AFTER = """
DO $$BEGIN
 IF EXISTS (SELECT * FROM original_rows EXCEPT SELECT * FROM executive_nexus.factory_cron_watchdog_checks)
 OR (SELECT count(*) FROM executive_nexus.factory_cron_watchdog_checks) <> 8
 THEN RAISE EXCEPTION 'historical rows changed'; END IF;
 IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='executive_nexus.factory_cron_watchdog_checks'::regclass)
 THEN RAISE EXCEPTION 'RLS disabled'; END IF;
 IF has_table_privilege('anon','executive_nexus.factory_cron_watchdog_checks','SELECT')
 OR has_function_privilege('authenticated','executive_nexus.run_factory_cron_watchdog()','EXECUTE')
 THEN RAISE EXCEPTION 'private privileges exposed'; END IF;
 RAISE NOTICE 'PASS historical rows and private access';
END$$;
INSERT INTO executive_nexus.factory_cron_watchdog_checks(slot,jobid,jobname,expected_run_at,verdict)
VALUES ('2026-11-23 08:00+00',99,'fixture','2026-11-23 08:19+00','RUN_STATUS_UNCERTAIN_NO_REPLAY');
DO $$BEGIN
 BEGIN
 UPDATE executive_nexus.factory_cron_watchdog_checks SET verdict='INVALID' WHERE jobid=99;
 RAISE EXCEPTION 'invalid verdict accepted';
 EXCEPTION WHEN check_violation THEN NULL; END;
 RAISE NOTICE 'PASS new verdict accepted and invalid verdict rejected';
END$$;
INSERT INTO cron.job VALUES
(26,true,'aeos2047-factory-reviewonly-router-15min','4,19,34,49 * * * *','select executive_nexus.run_factory_review_cycle();'),
(27,true,'aeos2047-autonomous-market-source-failover-hourly','16 * * * *','select executive_nexus.run_market_failover_check();');
INSERT INTO cron.job_run_details VALUES (26,now()-interval '1 minute','running'),(27,now()-interval '1 minute','starting');
INSERT INTO executive_nexus.factory_review_cycles VALUES (now()-interval '2 days');
INSERT INTO executive_nexus.market_failover_checks VALUES (now()-interval '2 days');
SELECT executive_nexus.run_factory_cron_watchdog();
SELECT executive_nexus.run_factory_cron_watchdog();
DO $$BEGIN
 IF EXISTS(SELECT FROM executive_nexus.test_replays) THEN RAISE EXCEPTION 'inflight replay'; END IF;
 IF EXISTS(SELECT FROM executive_nexus.factory_cron_watchdog_checks
 WHERE slot=date_trunc('hour',now()) AND retry_attempts<>0) THEN RAISE EXCEPTION 'inflight retry recorded'; END IF;
 RAISE NOTICE 'PASS full router rejects inflight replay on repeat calls';
END$$;
"""
ROLLBACK_CHECK = """
DO $$DECLARE s text; v text; BEGIN
 FOREACH s IN ARRAY ARRAY['running','starting','failed','succeeded'] LOOP
 v:=executive_nexus.factory_watchdog_verdict(true,true,'2026-11-23 08:19+00','2026-11-22 08:00+00',
 '2026-11-23 08:20+00',s,'2026-11-23 08:26+00');
 IF v IS DISTINCT FROM CASE WHEN s='succeeded' THEN 'HEALTHY' ELSE 'RUN_STATUS_UNCERTAIN_NO_REPLAY' END
 THEN RAISE EXCEPTION 'freeze mismatch % %',s,v; END IF;
 END LOOP;
 IF EXISTS(SELECT * FROM original_rows EXCEPT SELECT * FROM executive_nexus.factory_cron_watchdog_checks)
 THEN RAISE EXCEPTION 'freeze changed history'; END IF;
 IF has_function_privilege('anon','executive_nexus.factory_watchdog_verdict(boolean,boolean,timestamptz,timestamptz,timestamptz,text,timestamptz)','EXECUTE')
 THEN RAISE EXCEPTION 'freeze leaked privilege'; END IF;
 RAISE NOTICE 'PASS safe compensating rollback, history and privileges';
END$$;
ROLLBACK;
"""

def test_sql() -> str:
    return SETUP + MIGRATION.read_text() + AFTER + FREEZE.read_text() + ROLLBACK_CHECK

def main() -> int:
    # Fail closed: this script is intentionally limited to the isolated CI service.
    if os.getenv("PGHOST") != "127.0.0.1" or os.getenv("PGDATABASE") != "postgres" or os.getenv("PGUSER") != "postgres" or os.getenv("PGPASSWORD") != "isolated_ci_only":
        raise ValueError("ISOLATED_CI_DATABASE_REQUIRED")
    r = subprocess.run(["psql","-X","-v","ON_ERROR_STOP=1","-q"],
                       input=test_sql(),text=True,capture_output=True,timeout=60)
    print(r.stderr)
    if r.returncode:
        return r.returncode
    print("POSTGRES_WATCHDOG_MIGRATION: full source, legacy constraint, preserved history, repeat routing, compensating freeze PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
