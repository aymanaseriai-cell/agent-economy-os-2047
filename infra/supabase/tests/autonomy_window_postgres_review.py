#!/usr/bin/env python3
"""Synthetic PostgreSQL rehearsal only; never connect to production."""
from pathlib import Path
import os
import subprocess

SOURCE = Path(__file__).resolve().parents[1] / "factory_autonomy_evidence_20261121.sql"
SETUP = """
BEGIN;
CREATE SCHEMA executive_nexus;
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE TABLE executive_nexus.autonomy_episode_log (
 episode_key text PRIMARY KEY, owner_role text, trigger_type text, trigger_ref text,
 triggered_at timestamptz, finished_at timestamptz, result_status text,
 eligible_routine boolean, is_synthetic boolean, human_interventions integer,
 evidence_ref text, provider_verified boolean, controls_passed boolean,
 policy_violation boolean, recorded_at timestamptz, note text
);
INSERT INTO executive_nexus.autonomy_episode_log
SELECT role,role,'SCHEDULED','fixture',now()-interval '1 day',now()-interval '23 hours',
'VERIFIED',true,false,0,role,true,true,false,now(),'fixture'
FROM unnest(ARRAY['CEO','CTO','CRO','COO_CFO']) role;
"""
CHECK = """
DO $$DECLARE v record; BEGIN
 SELECT * INTO v FROM executive_nexus.factory_autonomy_evidence_14d;
 IF v.eligible_routine_episodes <> 4 OR v.recorded_verified_episodes <> 4
 OR v.full_company_autonomy_verdict <> 'NOT_VERIFIED_FULL_COMPANY_AUTONOMY'
 THEN RAISE EXCEPTION 'insufficient history should remain unverified'; END IF;
END$$;
INSERT INTO executive_nexus.autonomy_episode_log
SELECT 'old',owner_role,trigger_type,trigger_ref,now()-interval '15 days',now()-interval '15 days',
result_status,eligible_routine,is_synthetic,human_interventions,evidence_ref,provider_verified,
controls_passed,policy_violation,recorded_at,note FROM executive_nexus.autonomy_episode_log WHERE episode_key='CEO';
INSERT INTO executive_nexus.autonomy_episode_log
SELECT key,'CTO','SCHEDULED','fixture',triggered,finished,'VERIFIED',true,false,0,proof,true,true,false,now(),'fixture'
FROM (VALUES
 ('future',now()+interval '1 day',now()+interval '2 days','future'),
 ('unfinished',now()-interval '1 hour',NULL::timestamptz,'unfinished'),
 ('futurefinish',now()-interval '1 hour',now()+interval '1 day','futurefinish'),
 ('reverse',now()-interval '1 hour',now()-interval '2 hours','reverse'),
 ('blank',now()-interval '1 hour',now(),'   '),
 ('repeat',now()-interval '1 hour',now(),'CTO')
) AS x(key,triggered,finished,proof);
DO $$DECLARE v record; BEGIN
 SELECT * INTO v FROM executive_nexus.factory_autonomy_evidence_14d;
 IF v.eligible_routine_episodes <> 9 OR v.recorded_verified_episodes <> 5
 OR v.distinct_provider_proof_references <> 4 OR v.executive_roles_with_verified_episodes <> 4
 OR v.full_company_autonomy_verdict <> 'INDEPENDENT_FULL_COMPANY_VALIDATION_STILL_REQUIRED'
 THEN RAISE EXCEPTION 'window or proof count mismatch: %',row_to_json(v); END IF;
 IF has_table_privilege('anon','executive_nexus.factory_autonomy_evidence_14d','SELECT')
 OR has_table_privilege('authenticated','executive_nexus.factory_autonomy_evidence_14d','SELECT')
 THEN RAISE EXCEPTION 'private view exposed'; END IF;
END$$;
ROLLBACK;
"""

def main():
    expected = {"PGHOST":"127.0.0.1","PGDATABASE":"postgres","PGUSER":"postgres","PGPASSWORD":"isolated_ci_only"}
    if any(os.environ.get(k) != v for k,v in expected.items()):
        raise ValueError("ISOLATED_CI_DATABASE_REQUIRED")
    subprocess.run(["psql","-X","-v","ON_ERROR_STOP=1","-q"],
                   input=SETUP+SOURCE.read_text(encoding="utf-8")+CHECK,
                   text=True,check=True,timeout=60)
    print("AUTONOMY_WINDOW: history, future/unfinished/reversed timestamps, blank and repeated proofs, private ACL PASS")

if __name__ == "__main__":
    main()
