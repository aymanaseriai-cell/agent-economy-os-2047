-- REVIEW-ONLY EMERGENCY ROLLBACK: disable automatic replay without restoring
-- the unsafe production replay verdict. Never deploy without issue #98 approval.
-- This compensating function is valid ONLY after the reviewed watchdog schema
-- migration permits 'RUN_STATUS_UNCERTAIN_NO_REPLAY' in the verdict check.
-- It preserves healthy observations and scheduler configuration; it authorizes
-- NO watchdog replay for failed, absent, running, queued or uncertain jobs.
-- A deployment operator must independently verify compatibility and rollback.
CREATE OR REPLACE FUNCTION executive_nexus.factory_watchdog_verdict(
  p_enabled boolean,
  p_config_matches boolean,
  p_due timestamptz,
  p_first_seen timestamptz,
  p_last_run timestamptz,
  p_last_status text,
  p_now timestamptz
)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
 SELECT CASE
 WHEN NOT coalesce(p_enabled,false) THEN 'PAUSED_NO_OVERRIDE'
 WHEN NOT coalesce(p_config_matches,false) THEN 'CONFIG_DRIFT_BLOCKED'
 WHEN p_due IS NULL OR p_now IS NULL THEN 'RUN_STATUS_UNCERTAIN_NO_REPLAY'
 WHEN p_first_seen IS NULL OR p_due <= p_first_seen THEN 'WARMUP_NOT_DUE'
 WHEN p_due > p_now - interval '4 minutes' THEN 'WAIT_EXPECTED_RUN'
 -- Even apparently successful runs with impossible timestamps are uncertain.
 WHEN p_last_run IS NOT NULL AND p_last_run > p_now
   THEN 'RUN_STATUS_UNCERTAIN_NO_REPLAY'
 WHEN p_last_run >= p_due AND p_last_status = 'succeeded' THEN 'HEALTHY'
 -- The freeze rollback NEVER emits REPLAY_ELIGIBLE or invokes a job.
 ELSE 'RUN_STATUS_UNCERTAIN_NO_REPLAY' END
$function$;
REVOKE ALL ON FUNCTION executive_nexus.factory_watchdog_verdict(
 boolean,boolean,timestamptz,timestamptz,timestamptz,text,timestamptz)
 FROM PUBLIC,anon,authenticated;
