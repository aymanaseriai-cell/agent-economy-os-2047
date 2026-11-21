-- Agent Economy OS 2047: private review-only fallback acceptance loop
-- LIVE Supabase control-plane functions, source snapshot 2026-11-21.
-- Do not auto-promote to main/prod: release issue #98 OPEN and no independent approval.
-- No financial actions, customer messages, production code changes or 12 independent model sessions.
-- Pre-existing job 26 invokes run_factory_review_cycle() every 15 minutes.
-- This file versions private schema changes for review; it does not self-schedule.
CREATE OR REPLACE FUNCTION executive_nexus.complete_bounded_failover_review(p_dry_run boolean DEFAULT false)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE
 v_route record;
 v_incident record;
 v_order record;
 v_recent record;
 v_n integer;
 v_good integer;
 v_latest timestamptz;
 v_oldest timestamptz;
 v_receipts jsonb;
 v_verdict text;
 v_proof text := 'https://api.basedagents.ai/v1/tasks?status=open&limit=100';
 v_changed integer := 0;
 v_work_key text := 'AEOS2047:LIVE:INCIDENT:'||md5('AEOS2047:INCIDENT:MARKET_SOURCE:agentsouk');
 v_task_id text := 'AEOS2047-AUTO-REVIEW-'||md5('AEOS2047:INCIDENT:MARKET_SOURCE:agentsouk');
BEGIN
  IF NOT pg_catalog.pg_try_advisory_xact_lock(2047,918) THEN
    RETURN jsonb_build_object('outcome','ANOTHER_RECONCILIATION_IN_FLIGHT','dry_run',p_dry_run);
  END IF;
  SELECT state,allowed_sources,blocked_sources,checked_at INTO v_route
    FROM executive_nexus.market_failover_state
    WHERE route_key='agent_bounty_readonly_discovery';
  SELECT incident_state,source_state,last_checked_at INTO v_incident
    FROM executive_nexus.incident_ledger
    WHERE incident_key='AEOS2047:INCIDENT:MARKET_SOURCE:agentsouk';
  SELECT w.work_status,t.status task_status INTO v_order
    FROM executive_nexus.work_dispatch w
    JOIN executive_nexus.tasks t ON t.task_id=w.task_id
    WHERE w.work_key=v_work_key AND w.task_id=v_task_id
      AND w.owner_role='COO_CFO' AND w.action_code='REVIEW_UPSTREAM_INCIDENT';

  SELECT count(*)::integer,
         count(*) FILTER (
           WHERE status_code=200 AND checked_at IS NOT NULL
             AND checked_at>=requested_at AND checked_at<=now()
             AND NULLIF(btrim(COALESCE(error,'')),'') IS NULL
             AND funded_relevant_count IS NOT NULL
             AND funded_relevant_count>=0
             AND jsonb_typeof(funded_relevant)='array')::integer,
         max(requested_at),min(requested_at),
         coalesce(jsonb_agg(jsonb_build_object(
           'request_id',request_id,'requested_at',requested_at,
           'checked_at',checked_at,'status_code',status_code,
           'funded_relevant_count',funded_relevant_count)
           ORDER BY requested_at DESC),'[]'::jsonb)
  INTO v_n,v_good,v_latest,v_oldest,v_receipts
  FROM (
    SELECT request_id,requested_at,checked_at,status_code,error,
           funded_relevant_count,funded_relevant
    FROM public.agent_economy_bounty_monitor
    WHERE market='basedagents'
    ORDER BY requested_at DESC,request_id DESC LIMIT 2
  ) recent;
  IF v_order.work_status IS NULL OR v_order.task_status IS NULL THEN
    RETURN jsonb_build_object('outcome','MISSING_OWNED_INCIDENT_WORK_ORDER','dry_run',p_dry_run,'external_actions',0);
  END IF;
  SELECT executive_nexus.fallback_acceptance_verdict(
    v_route.state,v_route.allowed_sources,v_route.blocked_sources,
    now()-v_route.checked_at,v_n,v_good,now()-v_latest,
    now()-v_oldest,v_latest-v_oldest,
    v_incident.incident_state='OPEN')
   INTO v_verdict;
  IF p_dry_run THEN
    RETURN jsonb_build_object('outcome',v_verdict,'dry_run',true,
      'current_task_status',v_order.task_status,'current_work_status',v_order.work_status,
      'sample_count',v_n,'valid_samples',v_good,'receipts',v_receipts,
      'vendor_incident_open',v_incident.incident_state='OPEN',
      'vendor_repair_claimed',false,'external_actions',0);
  END IF;
  IF v_verdict='VERIFIED_BOUNDED_FALLBACK'
     AND v_order.work_status IN ('QUEUED','IN_PROGRESS','BLOCKED')
     AND v_order.task_status IN ('QUEUED','BLOCKED') THEN
    UPDATE executive_nexus.work_dispatch
     SET work_status='VERIFIED',proof_ref=v_proof,
         completion_note=(
           'Internal zero-cost alternative source is technically available, based on TWO separate '||
           'provider-backed HTTP 200 samples; receipt detail: '||left(v_receipts::text,1350)||
           '. AgentSouk external DNS incident remains OPEN; no source repair, funded '||
           'opportunity, buyer, revenue, customer outreach, automated code patch or paid delivery.'
         ),
         last_observed_at=now(),updated_at=now()
     WHERE work_key=v_work_key
       AND work_status IN ('QUEUED','IN_PROGRESS','BLOCKED');
    GET DIAGNOSTICS v_changed=ROW_COUNT;
    IF v_changed=1 THEN
      UPDATE executive_nexus.tasks
         SET status='VERIFIED',blocker=NULL,
             evidence_refs=evidence_refs||jsonb_build_array(v_proof),
             next_action='Bounded alternative source accepted internally. Continue monitoring actual AgentSouk DNS; keep external incident OPEN until independent recovery. Do not infer buyer demand or payment.',
             updated_at=now()
       WHERE task_id=v_task_id
         AND status IN ('QUEUED','BLOCKED');
      INSERT INTO executive_nexus.audit_events
       (event_key,task_id,owner_role,event_type,result_status,evidence_ref,note)
      VALUES
       ('AEOS2047:INTERNAL:ALTERNATE_DISCOVERY:'||v_latest::date::text||':'||
            replace(to_char(v_latest AT TIME ZONE 'UTC','HH24MI'),':',''),
        v_task_id,'COO_CFO','INTERNAL_PROVIDER_BACKED_FALLBACK_ACCEPTANCE',
        'VERIFIED_BOUNDED_FALLBACK_NOT_VENDOR_RECOVERY',v_proof,
        'Two distinct completed real provider observations: '||left(v_receipts::text,1200)||
        '. Private work-order acceptance only; original external source incident remains open.')
      ON CONFLICT(event_key) DO NOTHING;
    END IF;
  END IF;
  RETURN jsonb_build_object('outcome',
    CASE WHEN v_changed=1 THEN 'WORK_ORDER_COMPLETED_ON_PROVIDER_EVIDENCE'
         WHEN v_verdict='VERIFIED_BOUNDED_FALLBACK' AND v_order.work_status='VERIFIED'
         THEN 'ALREADY_COMPLETED_NO_DUPLICATE'
         ELSE 'NO_CHANGE_WAIT_FOR_ELIGIBLE_EVIDENCE' END,
      'evidence_status',v_verdict,'dry_run',false,
      'changed_rows',v_changed,'checked_receipts',v_receipts,
      'vendor_incident_open',v_incident.incident_state='OPEN',
      'vendor_repair_claimed',false,
      'external_network_requests',0,'customer_contacts',0,
      'financial_actions',0,'autonomous_llm_workers_instantiated',0);
END;
$function$;

CREATE OR REPLACE FUNCTION executive_nexus.fallback_acceptance_verdict(p_route_state text, p_allowed_sources jsonb, p_blocked_sources jsonb, p_route_age interval, p_sample_count integer, p_good_count integer, p_latest_age interval, p_oldest_age interval, p_spacing interval, p_incident_open boolean)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
 SELECT CASE
  WHEN p_route_state IS DISTINCT FROM 'DEGRADED_HEALTHY_FALLBACK'
    OR p_allowed_sources IS NULL
    OR p_allowed_sources <> '["basedagents"]'::jsonb
    OR p_blocked_sources IS NULL
    OR NOT (p_blocked_sources ? 'agentsouk')
    OR p_route_age IS NULL OR p_route_age < interval '0 seconds'
    OR p_route_age > interval '95 minutes'
    OR p_sample_count IS DISTINCT FROM 2
    OR p_good_count IS DISTINCT FROM 2
    OR p_latest_age IS NULL OR p_latest_age < interval '0 seconds'
    OR p_latest_age > interval '95 minutes'
    OR p_oldest_age IS NULL OR p_oldest_age < interval '0 seconds'
    OR p_oldest_age > interval '185 minutes'
    OR p_spacing IS NULL OR p_spacing < interval '25 minutes'
    OR p_incident_open IS DISTINCT FROM TRUE
   THEN 'NOT_ACCEPTABLE'
  ELSE 'VERIFIED_BOUNDED_FALLBACK'
 END;
$function$;

CREATE OR REPLACE FUNCTION executive_nexus.run_factory_review_cycle()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE
 v_slot timestamptz := date_bin(interval '15 minutes', now(), '2020-01-01 00:00:00+00'::timestamptz);
 v_worker_count integer;
 v_executive_count integer;
 v_order_count integer;
 v_new_orders integer := 0;
 v_source_cycle timestamptz;
 v_incident record;
 v_manager record;
 v_order record;
 v_new_work_key text;
 v_task_id text;
 v_work_key text;
 v_decisions jsonb := '[]'::jsonb;
 v_decision text;
BEGIN
 SELECT count(*) INTO v_worker_count FROM executive_nexus.worker_registry
 WHERE status='REVIEW_ONLY' AND worker_id ~ '^AEOS-W(0[1-9]|1[0-2])$';
 SELECT count(*) INTO v_executive_count FROM executive_nexus.executives
 WHERE enabled IS TRUE AND role IN ('CEO','CTO','CRO','COO_CFO');
 SELECT count(*) INTO v_order_count FROM executive_nexus.work_dispatch
 WHERE work_key LIKE 'AEOS2047:FACTORY:20261121:AEOS-W%';
 IF v_worker_count <> 12 OR v_executive_count <> 4 OR v_order_count <> 12
    OR (SELECT count(*) FROM executive_nexus.worker_registry) <> 12
 THEN RAISE EXCEPTION 'FACTORY_IDENTITY_OR_ORDER_INVARIANT_FAILED workers:% executives:% orders:%',
         v_worker_count,v_executive_count,v_order_count;
 END IF;
 SELECT max(cycle_window) INTO v_source_cycle FROM executive_nexus.autonomy_cycles;
 IF v_source_cycle IS NULL THEN RAISE EXCEPTION 'MISSING_PRIOR_EXECUTIVE_OBSERVATION'; END IF;

 -- Create at most six new, idempotent *review-only* work orders for observed upstream incidents.
 -- Never assume a source outage was repaired or an actual worker agent was spawned.
 FOR v_incident IN
   SELECT incident_key,source_kind,source_name,owner_role,incident_state,source_state,last_checked_at
   FROM executive_nexus.incident_ledger
   WHERE incident_state='OPEN' AND owner_role='COO_CFO'
     AND source_kind='MARKET_SOURCE' AND last_checked_at>=now()-interval '45 minutes'
   ORDER BY last_checked_at DESC,incident_key LIMIT 6
 LOOP
   v_task_id := 'AEOS2047-AUTO-REVIEW-'||md5(v_incident.incident_key);
   v_work_key := 'AEOS2047:LIVE:INCIDENT:'||md5(v_incident.incident_key);
   INSERT INTO executive_nexus.tasks
     (task_id,owner_role,goal,status,acceptance_test,next_action,evidence_refs)
   VALUES
     (v_task_id,'COO_CFO',
      'Review external upstream market-source failure: '||left(v_incident.source_name,80),
      'QUEUED',
      'Verify fresh provider-backed recovery in at least two independent samples or document a bounded zero-cost fallback. Do not invent funding, buyers, or settlement.',
      'COO/CFO: compare latest upstream response, diagnose DNS/vendor vs our service and propose reversible fallback. Never contact vendors without authorization or make payment.',
      '[]'::jsonb)
   ON CONFLICT (task_id) DO NOTHING;
   v_new_work_key := null;
   INSERT INTO executive_nexus.work_dispatch
      (work_key,task_id,owner_role,action_code,work_status,priority,source_cycle,completion_note)
   VALUES
      (v_work_key,v_task_id,'COO_CFO','REVIEW_UPSTREAM_INCIDENT','QUEUED',1,v_source_cycle,
       'AUTO_QUEUED_REVIEW_ONLY from fresh existing internal incident; not service recovery, human approval or independently verified task execution.')
   ON CONFLICT(work_key) DO NOTHING RETURNING work_key INTO v_new_work_key;
   IF v_new_work_key IS NOT NULL THEN
      v_new_orders := v_new_orders+1;
      INSERT INTO executive_nexus.audit_events
        (event_key,task_id,owner_role,event_type,result_status,evidence_ref,note)
      VALUES
        ('AEOS2047:FACTORY:INCIDENT:'||md5(v_incident.incident_key),
         v_task_id,'COO_CFO','SYSTEM_INTERNAL_INCIDENT_TO_MANAGER_ROUTING',
         'QUEUED_REVIEW_ONLY',NULL,
         'An existing upstream incident was automatically assigned to COO/CFO for read-only investigation. No engineer action, real customer, repaired outage, outreach or revenue is implied.')
      ON CONFLICT(event_key) DO NOTHING;
   END IF;
 END LOOP;

 -- Complete a bounded internal fallback review ONLY after independent provider evidence.
 -- This is internal continuity, NOT upstream DNS repair, sales, or a separate model agent.
 PERFORM executive_nexus.complete_bounded_failover_review(false);

 FOR v_manager IN
   SELECT role FROM executive_nexus.executives WHERE enabled IS TRUE
      AND role IN ('CEO','CTO','CRO','COO_CFO')
   ORDER BY CASE role WHEN 'CEO' THEN 1 WHEN 'CTO' THEN 2
                      WHEN 'CRO' THEN 3 ELSE 4 END
 LOOP
   SELECT work_key,action_code,work_status,priority INTO v_order
   FROM executive_nexus.work_dispatch
   WHERE owner_role=v_manager.role
      AND (work_key LIKE 'AEOS2047:FACTORY:20261121:AEOS-W%'
           OR work_key LIKE 'AEOS2047:LIVE:INCIDENT:%')
      AND work_status IN ('QUEUED','IN_PROGRESS','NEEDS_APPROVAL','BLOCKED')
   ORDER BY CASE work_status WHEN 'QUEUED' THEN 1 WHEN 'IN_PROGRESS' THEN 2
                WHEN 'NEEDS_APPROVAL' THEN 3 ELSE 4 END,
            priority,work_key
   LIMIT 1;
   IF NOT FOUND THEN
      v_decisions := v_decisions || jsonb_build_array(
        jsonb_build_object('executive',v_manager.role,'decision','NO_ELIGIBLE_NEW_WORK',
                           'worker_key',NULL,'execution_verified',false));
   ELSE
      v_decision := CASE v_order.work_status
          WHEN 'QUEUED' THEN 'READY_FOR_BOUNDED_MANAGER_EXECUTION'
          WHEN 'IN_PROGRESS' THEN 'VERIFY_EXISTING_WORK_BEFORE_RETRY'
          WHEN 'NEEDS_APPROVAL' THEN 'ESCALATE_HUMAN_APPROVAL'
          ELSE 'WAIT_FOR_NEW_EXTERNAL_EVIDENCE' END;
      v_decisions := v_decisions || jsonb_build_array(
        jsonb_build_object('executive',v_manager.role,'decision',v_decision,
          'work_key',v_order.work_key,'action',v_order.action_code,
          'state',v_order.work_status,'priority',v_order.priority,
          'execution_verified',false,'money_moved',false));
   END IF;
 END LOOP;
 INSERT INTO executive_nexus.factory_review_cycles
    (cycle_window,observed_at,registered_workers,enabled_executives,decisions,
     new_incident_work_orders)
 VALUES (v_slot,now(),v_worker_count,v_executive_count,v_decisions,v_new_orders)
 ON CONFLICT(cycle_window) DO UPDATE
 SET observed_at=excluded.observed_at,
     decisions=excluded.decisions,
     new_incident_work_orders=executive_nexus.factory_review_cycles.new_incident_work_orders
                              + excluded.new_incident_work_orders;
 RETURN jsonb_build_object('cycle',v_slot,'registered_workers',v_worker_count,
     'executives',v_executive_count,'decisions',v_decisions,
     'new_review_only_incident_orders',v_new_orders,
     'actual_worker_actions',0,'production_changes',0,
     'money_moved',false,'external_contacts',0,
     'real_company_autonomy_proven',false);
END
$function$;

REVOKE ALL ON FUNCTION executive_nexus.fallback_acceptance_verdict(text,jsonb,jsonb,interval,integer,integer,interval,interval,interval,boolean) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION executive_nexus.complete_bounded_failover_review(boolean) FROM PUBLIC,anon,authenticated;
-- Source control parity note: original incident remains OPEN if upstream DNS is broken.
