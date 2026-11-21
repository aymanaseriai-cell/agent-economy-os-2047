-- Agent Economy OS 2047: REVIEW-ONLY executive control-plane source snapshot.
-- 2026-11-21: already applied to private Supabase executive_nexus.
-- NOT connected to GitHub or CI auto-deploy; independent review required.
-- Only creates internal decision records and idempotent incident work orders.
-- Never touches production service code, payments, customers or trading.
CREATE TABLE IF NOT EXISTS executive_nexus.factory_review_cycles (
 cycle_window timestamptz PRIMARY KEY,
 observed_at timestamptz NOT NULL DEFAULT now(),
 registered_workers integer NOT NULL CHECK(registered_workers=12),
 enabled_executives integer NOT NULL CHECK(enabled_executives=4),
 decisions jsonb NOT NULL CHECK(jsonb_typeof(decisions)='array'),
 new_incident_work_orders integer NOT NULL DEFAULT 0 CHECK(new_incident_work_orders BETWEEN 0 AND 6),
 actual_worker_actions integer NOT NULL DEFAULT 0 CHECK(actual_worker_actions=0),
 external_customer_contacts integer NOT NULL DEFAULT 0 CHECK(external_customer_contacts=0),
 production_changes integer NOT NULL DEFAULT 0 CHECK(production_changes=0),
 scope_note text NOT NULL DEFAULT 'Scheduled review-only routing; never count as paid delivery or 12 autonomous LLM workers'
);
REVOKE ALL ON TABLE executive_nexus.factory_review_cycles FROM PUBLIC, anon, authenticated;
ALTER TABLE executive_nexus.factory_review_cycles ENABLE ROW LEVEL SECURITY;

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

REVOKE ALL ON FUNCTION executive_nexus.run_factory_review_cycle() FROM PUBLIC, anon, authenticated;

-- Deployed cron registration must be independently reviewed, not replayed by this file.
-- Name: aeos2047-factory-reviewonly-router-15min, job 26
-- Schedule: 4,19,34,49 * * * *
-- Command: SELECT executive_nexus.run_factory_review_cycle();
-- Release issue #98 remains open and forbids unapproved production promotion.
