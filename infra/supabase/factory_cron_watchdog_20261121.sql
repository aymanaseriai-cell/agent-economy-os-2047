-- Agent Economy OS 2047 — PRIVATE BOUNDED CRON SELF-REPLAY WATCHDOG.
-- The previous version is deployed in Supabase. THIS safety correction is REVIEW-ONLY.
-- GitHub is a source-review snapshot; do not deploy without independent approval.
-- NO automatic deployment; release approval issue #98 remains open.
-- Calls only approved private read-only DB functions, at most once/job/hour.
-- Never overrides an operator-paused job or changed cron configuration.
CREATE TABLE IF NOT EXISTS executive_nexus.factory_cron_watchdog_checks (
 slot timestamptz NOT NULL,
 jobid bigint NOT NULL,
 jobname text NOT NULL,
 expected_run_at timestamptz NOT NULL,
 observed_latest_run_at timestamptz,
 observed_cron_status text,
 verdict text NOT NULL CHECK(verdict IN (
   'EVALUATING','HEALTHY','PAUSED_NO_OVERRIDE','CONFIG_DRIFT_BLOCKED',
   'WARMUP_NOT_DUE','WAIT_EXPECTED_RUN','RUN_STATUS_UNCERTAIN_NO_REPLAY',
   'READONLY_REPLAY_SUCCEEDED','READONLY_REPLAY_FAILED')),
 retry_attempts integer NOT NULL DEFAULT 0 CHECK(retry_attempts BETWEEN 0 AND 1),
 internal_replay_result jsonb NOT NULL DEFAULT '{}'::jsonb,
 checked_at timestamptz NOT NULL DEFAULT now(),
 execution_origin text NOT NULL DEFAULT 'UNVERIFIED'
   CHECK(execution_origin IN('USER_REQUEST','UNVERIFIED','INDEPENDENT_SCHEDULED_VERIFIED')),
 PRIMARY KEY(slot,jobid),
 CONSTRAINT no_external_actions_watchdog CHECK(jsonb_typeof(internal_replay_result)='object')
);
ALTER TABLE executive_nexus.factory_cron_watchdog_checks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON executive_nexus.factory_cron_watchdog_checks FROM PUBLIC,anon,authenticated;

-- Existing private deployments need this narrowly scoped constraint migration.
-- This file is not connected to automatic migrations or cron deploys.
ALTER TABLE executive_nexus.factory_cron_watchdog_checks
  DROP CONSTRAINT IF EXISTS factory_cron_watchdog_checks_verdict_check;
ALTER TABLE executive_nexus.factory_cron_watchdog_checks
  ADD CONSTRAINT factory_cron_watchdog_checks_verdict_check CHECK(verdict IN (
    'EVALUATING','HEALTHY','PAUSED_NO_OVERRIDE','CONFIG_DRIFT_BLOCKED',
    'WARMUP_NOT_DUE','WAIT_EXPECTED_RUN','RUN_STATUS_UNCERTAIN_NO_REPLAY',
    'READONLY_REPLAY_SUCCEEDED','READONLY_REPLAY_FAILED'));

CREATE OR REPLACE FUNCTION executive_nexus.factory_watchdog_verdict(p_enabled boolean, p_config_matches boolean, p_due timestamp with time zone, p_first_seen timestamp with time zone, p_last_run timestamp with time zone, p_last_status text, p_now timestamp with time zone)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
 SELECT CASE
 WHEN NOT coalesce(p_enabled,false) THEN 'PAUSED_NO_OVERRIDE'
 WHEN NOT coalesce(p_config_matches,false) THEN 'CONFIG_DRIFT_BLOCKED'
 WHEN p_first_seen IS NULL OR p_due<=p_first_seen THEN 'WARMUP_NOT_DUE'
 WHEN p_due IS NULL OR p_now IS NULL THEN 'RUN_STATUS_UNCERTAIN_NO_REPLAY'
 WHEN p_due>p_now-interval '4 minutes' THEN 'WAIT_EXPECTED_RUN'
 -- Inconsistent missing timestamps/status must never authorize a replay.
 WHEN p_last_run IS NULL AND p_last_status IS NOT NULL
   THEN 'RUN_STATUS_UNCERTAIN_NO_REPLAY'
 -- A still-running, incomplete, or unknown cron status must not be replayed.
 WHEN p_last_run IS NOT NULL AND (p_last_status IS NULL OR p_last_status NOT IN ('succeeded','failed'))
   THEN 'RUN_STATUS_UNCERTAIN_NO_REPLAY'
 -- Future-dated run evidence is inconsistent, even when status is terminal.
 WHEN p_last_run IS NOT NULL AND p_last_run > p_now
   THEN 'RUN_STATUS_UNCERTAIN_NO_REPLAY'
 WHEN p_last_run>=p_due AND p_last_status='succeeded' THEN 'HEALTHY'
 ELSE 'REPLAY_ELIGIBLE' END
$function$;

CREATE OR REPLACE FUNCTION executive_nexus.run_factory_cron_watchdog()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE
 v_slot timestamptz := date_trunc('hour',now());
 v_job record;
 v_active bool;
 v_jobname text;
 v_schedule text;
 v_command text;
 v_last_run timestamptz;
 v_last_status text;
 v_first_seen timestamptz;
 v_expected timestamptz;
 v_config_matches bool;
 v_decision text;
 v_attempt jsonb;
 v_err text;
 v_inserted int;
 v_results jsonb := '[]'::jsonb;
BEGIN
 IF NOT pg_catalog.pg_try_advisory_xact_lock(2047,913) THEN
   RETURN jsonb_build_object('skipped','another private watchdog cycle in flight');
 END IF;
 FOR v_job IN
 SELECT * FROM (VALUES
  (26::bigint,'aeos2047-factory-reviewonly-router-15min'::text,'4,19,34,49 * * * *'::text,
    'select executive_nexus.run_factory_review_cycle();'::text,19),
  (27::bigint,'aeos2047-autonomous-market-source-failover-hourly'::text,'16 * * * *'::text,
    'select executive_nexus.run_market_failover_check();'::text,16)
 ) AS j(jobid,jobname,schedule,command,due_minute)
 LOOP
   SELECT active,jobname,schedule,command INTO v_active,v_jobname,v_schedule,v_command
   FROM cron.job WHERE jobid=v_job.jobid;
   SELECT start_time,status INTO v_last_run,v_last_status FROM cron.job_run_details
     WHERE jobid=v_job.jobid ORDER BY start_time DESC LIMIT 1;
   v_expected := v_slot+make_interval(mins=>v_job.due_minute);
   IF v_job.jobid=26 THEN
     SELECT min(observed_at) INTO v_first_seen FROM executive_nexus.factory_review_cycles;
   ELSE
     SELECT min(checked_at) INTO v_first_seen FROM executive_nexus.market_failover_checks;
   END IF;
   v_config_matches := (v_jobname IS NOT DISTINCT FROM v_job.jobname
                        AND v_schedule IS NOT DISTINCT FROM v_job.schedule
                        AND btrim(v_command) IS NOT DISTINCT FROM v_job.command);
   v_decision := executive_nexus.factory_watchdog_verdict(
     v_active,v_config_matches,v_expected,v_first_seen,v_last_run,v_last_status,now());
   v_inserted := 0;
   INSERT INTO executive_nexus.factory_cron_watchdog_checks
     (slot,jobid,jobname,expected_run_at,observed_latest_run_at,observed_cron_status,
      verdict,retry_attempts,internal_replay_result)
   VALUES
     (v_slot,v_job.jobid,v_job.jobname,v_expected,v_last_run,v_last_status,
      CASE WHEN v_decision='REPLAY_ELIGIBLE' THEN 'EVALUATING' ELSE v_decision END,
      CASE WHEN v_decision='REPLAY_ELIGIBLE' THEN 1 ELSE 0 END,
      jsonb_build_object('retry_needed',v_decision='REPLAY_ELIGIBLE',
                         'cron_schedule_unmodified',true,'production_change',false))
   -- An early same-hour observation must not suppress the later due-time
   -- inspection. Only replace unattempted preliminary verdicts; terminal
   -- verdicts and prior replay attempts remain immutable for the hour.
   ON CONFLICT(slot,jobid) DO UPDATE
   SET observed_latest_run_at=excluded.observed_latest_run_at,
       observed_cron_status=excluded.observed_cron_status,
       verdict=excluded.verdict,
       retry_attempts=excluded.retry_attempts,
       internal_replay_result=excluded.internal_replay_result,
       checked_at=now(),
       execution_origin='UNVERIFIED'
   WHERE executive_nexus.factory_cron_watchdog_checks.verdict
           IN ('WAIT_EXPECTED_RUN','WARMUP_NOT_DUE')
     AND executive_nexus.factory_cron_watchdog_checks.retry_attempts=0
     AND executive_nexus.factory_cron_watchdog_checks.verdict IS DISTINCT FROM excluded.verdict;
   GET DIAGNOSTICS v_inserted=ROW_COUNT;
   IF v_inserted=1 AND v_decision='REPLAY_ELIGIBLE' THEN
      BEGIN
        IF v_job.jobid=26 THEN
          v_attempt := executive_nexus.run_factory_review_cycle();
        ELSIF v_job.jobid=27 THEN
          v_attempt := executive_nexus.run_market_failover_check();
        END IF;
        UPDATE executive_nexus.factory_cron_watchdog_checks
        SET verdict='READONLY_REPLAY_SUCCEEDED',
           internal_replay_result=jsonb_build_object(
             'function_invoked',v_job.command,
             'result',v_attempt,'original_cron_recovered',false,
             'independent_llm_workers_instantiated',0,'production_change',false)
        WHERE slot=v_slot AND jobid=v_job.jobid;
        v_decision:='READONLY_REPLAY_SUCCEEDED';
      EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS v_err=MESSAGE_TEXT;
        UPDATE executive_nexus.factory_cron_watchdog_checks
        SET verdict='READONLY_REPLAY_FAILED',
            internal_replay_result=jsonb_build_object(
              'sqlstate',SQLSTATE,'error',left(coalesce(v_err,''),180),
              'another_automatic_retry_in_same_hour',false,'production_change',false)
        WHERE slot=v_slot AND jobid=v_job.jobid;
        v_decision:='READONLY_REPLAY_FAILED';
      END;
   ELSIF v_inserted=0 THEN
       SELECT verdict INTO v_decision FROM executive_nexus.factory_cron_watchdog_checks
         WHERE slot=v_slot AND jobid=v_job.jobid;
   END IF;
   v_results:=v_results||jsonb_build_array(jsonb_build_object(
     'jobid',v_job.jobid,'verdict',v_decision,'existing_hour_record',v_inserted=0,
     'retry_count_for_current_hour',(SELECT retry_attempts FROM executive_nexus.factory_cron_watchdog_checks
                                    WHERE slot=v_slot AND jobid=v_job.jobid)));
   v_active:=NULL;v_jobname:=NULL;v_schedule:=NULL;v_command:=NULL;
   v_last_run:=NULL;v_last_status:=NULL;v_first_seen:=NULL;
 END LOOP;
 RETURN jsonb_build_object(
  'slot',v_slot,'jobs',v_results,
  'external_network_calls_from_watchdog',0,'financial_actions',0,
  'customer_contacts',0,'production_changes',0,
  'full_company_autonomy_verified',false);
END
$function$;
REVOKE ALL ON FUNCTION executive_nexus.run_factory_cron_watchdog() FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION executive_nexus.factory_watchdog_verdict(
boolean,boolean,timestamptz,timestamptz,timestamptz,text,timestamptz)
FROM PUBLIC,anon,authenticated;

-- Registered live postgres cron job ID 28:
-- aeos2047-readonly-factory-scheduler-watchdog-hourly
-- 24 * * * *
-- select executive_nexus.run_factory_cron_watchdog();
-- Initial manual rows for slot 2026-11-21 20:00 UTC:
-- origin USER_REQUEST, job 26 HEALTHY, job 27 WARMUP_NOT_DUE.
-- First unattended job 28 run must be confirmed independently from cron.job_run_details.
