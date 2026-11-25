-- Agent Economy OS 2047: REVIEW-ONLY proposal; NOT DEPLOYED.
-- Automated independent scheduler-origin reconciliation with strict provider
-- cron provenance. Run only after issue #98 review, migration and authorization.
-- This function updates provenance flags only. It does NOT fabricate autonomous
-- successes, create extra episodes, contact prospects, deploy code or spend.
CREATE OR REPLACE FUNCTION executive_nexus.reconcile_factory_schedule_provenance()
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
 v_watchdog integer := 0;
 v_market integer := 0;
BEGIN
 IF NOT pg_catalog.pg_try_advisory_xact_lock(2047,918) THEN
    RETURN pg_catalog.jsonb_build_object('skipped','provenance reconciliation already running');
 END IF;

 -- Accept rows only if their check timestamp fell INSIDE the independently
 -- completed, successful run of the exact approved pg_cron job and command.
 WITH verified_cron AS (
  SELECT r.runid, r.start_time, r.end_time
  FROM cron.job_run_details r
  JOIN cron.job j ON j.jobid=r.jobid
  WHERE r.jobid=28 AND r.status='succeeded'
    AND r.end_time IS NOT NULL
    AND r.start_time>=now()-interval '48 hours'
    AND j.active IS TRUE
    AND j.jobname='aeos2047-readonly-factory-scheduler-watchdog-hourly'
    AND j.schedule='24 * * * *'
    AND pg_catalog.btrim(j.command)='select executive_nexus.run_factory_cron_watchdog();'
 ),
 changed AS (
  UPDATE executive_nexus.factory_cron_watchdog_checks c
   SET execution_origin='INDEPENDENT_SCHEDULED_VERIFIED'
  FROM verified_cron r
  WHERE c.execution_origin='UNVERIFIED'
    AND c.slot=pg_catalog.date_trunc('hour',r.start_time)
    AND c.checked_at>=r.start_time AND c.checked_at<=r.end_time
    AND c.jobid IN (26,27)
    AND c.verdict='HEALTHY' AND c.retry_attempts=0
  RETURNING c.slot,c.jobid
 )
 SELECT count(*) INTO v_watchdog FROM changed;

 WITH verified_cron AS (
  SELECT r.runid,r.start_time,r.end_time
  FROM cron.job_run_details r
  JOIN cron.job j ON j.jobid=r.jobid
  WHERE r.jobid=27 AND r.status='succeeded'
    AND r.end_time IS NOT NULL
    AND r.start_time>=now()-interval '48 hours'
    AND j.active IS TRUE
    AND j.jobname='aeos2047-autonomous-market-source-failover-hourly'
    AND j.schedule='16 * * * *'
    AND pg_catalog.btrim(j.command)='select executive_nexus.run_market_failover_check();'
 ),
 changed AS (
  UPDATE executive_nexus.market_failover_checks c
   SET execution_origin='INDEPENDENT_SCHEDULED_VERIFIED'
  FROM verified_cron r
  WHERE c.execution_origin='UNVERIFIED'
    AND c.slot=pg_catalog.date_trunc('hour',r.start_time)
    AND c.checked_at>=r.start_time AND c.checked_at<=r.end_time
    AND c.state='DEGRADED_HEALTHY_FALLBACK'
    AND c.allowed_sources='["basedagents"]'::jsonb
    AND c.actual_outbound_http_requests=0
    AND c.customer_contacts=0 AND c.payment_actions=0
    AND c.evidence #>> '{basedagents,recent_provider_replies,0,http_status}'='200'
    AND c.evidence #>> '{basedagents,recent_provider_replies,1,http_status}'='200'
    AND c.evidence #>> '{basedagents,recent_provider_replies,0,request_id}'
        IS DISTINCT FROM c.evidence #>> '{basedagents,recent_provider_replies,1,request_id}'
  RETURNING c.slot
 )
 SELECT count(*) INTO v_market FROM changed;

 RETURN pg_catalog.jsonb_build_object(
   'verified_watchdog_checks',v_watchdog,
   'verified_independent_market_checks',v_market,
   'eligible_for_new_autonomy_episodes',false,
   'external_network_calls',0,
   'actual_worker_actions',0,
   'financial_actions',0,
   'production_deployments',0);
END
$function$;

REVOKE ALL ON FUNCTION executive_nexus.reconcile_factory_schedule_provenance()
 FROM PUBLIC,anon,authenticated;

-- Suggested future schedule ONLY after approval: 25 * * * *
-- SELECT cron.schedule('aeos2047-cron-provenance-reconciler-hourly',
--   '25 * * * *','select executive_nexus.reconcile_factory_schedule_provenance();');
-- No cron.schedule call is executed by this review-only source.
