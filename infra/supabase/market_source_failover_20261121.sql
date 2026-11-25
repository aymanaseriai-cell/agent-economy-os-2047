-- Agent Economy OS 2047 / private zero-cost read-only market routing.
-- Source snapshot of live Supabase private control-plane at 2026-11-21.
-- Already applied in Supabase; GitHub branch is documentation/review only.
-- DO NOT wire to automatic prod deploy. Independent P0 release gate #98 remains OPEN.
-- This does NOT instantiate LLM agents, contact customers, move funds, place trades,
-- repair AgentSouk DNS, or certify provider/buyer/payment authenticity.
CREATE TABLE IF NOT EXISTS executive_nexus.market_failover_state (
 route_key text PRIMARY KEY CHECK(route_key='agent_bounty_readonly_discovery'),
 state text NOT NULL CHECK(state IN ('HEALTHY_MULTI_SOURCE','DEGRADED_HEALTHY_FALLBACK','HALTED_NO_TRUSTED_SOURCE')),
 allowed_sources jsonb NOT NULL CHECK(jsonb_typeof(allowed_sources)='array'),
 blocked_sources jsonb NOT NULL CHECK(jsonb_typeof(blocked_sources)='array'),
 evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='object'),
 checked_at timestamptz NOT NULL DEFAULT now(),
 last_transition_at timestamptz NOT NULL DEFAULT now(),
 read_only_mode boolean NOT NULL DEFAULT true CHECK(read_only_mode=true),
 money_moved boolean NOT NULL DEFAULT false CHECK(money_moved=false),
 buyer_contacted boolean NOT NULL DEFAULT false CHECK(buyer_contacted=false)
);
ALTER TABLE executive_nexus.market_failover_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON executive_nexus.market_failover_state FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS executive_nexus.market_failover_checks (
 slot timestamptz PRIMARY KEY,
 checked_at timestamptz NOT NULL DEFAULT now(),
 state text NOT NULL CHECK(state IN ('HEALTHY_MULTI_SOURCE','DEGRADED_HEALTHY_FALLBACK','HALTED_NO_TRUSTED_SOURCE')),
 allowed_sources jsonb NOT NULL CHECK(jsonb_typeof(allowed_sources)='array'),
 evidence jsonb NOT NULL,
 actual_outbound_http_requests integer NOT NULL DEFAULT 0 CHECK(actual_outbound_http_requests=0),
 customer_contacts integer NOT NULL DEFAULT 0 CHECK(customer_contacts=0),
 payment_actions integer NOT NULL DEFAULT 0 CHECK(payment_actions=0)
);
ALTER TABLE executive_nexus.market_failover_checks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON executive_nexus.market_failover_checks FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION executive_nexus.run_market_failover_check()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE
  v_slot timestamptz := date_trunc('hour',now());
  v_market text;
  v_total int;
  v_valid int;
  v_oldest timestamptz;
  v_latest timestamptz;
  v_receipts jsonb;
  v_allowed jsonb := '[]'::jsonb;
  v_blocked jsonb := '[]'::jsonb;
  v_evidence jsonb := '{}'::jsonb;
  v_state text;
  v_prior_state text;
  v_prior_allowed jsonb;
  v_transition boolean;
  v_source_ok boolean;
BEGIN
  IF NOT pg_catalog.pg_try_advisory_xact_lock(2047,912) THEN
    RETURN jsonb_build_object('skipped','another market-failover cycle is running','outbound_http',0);
  END IF;
  FOR v_market IN SELECT name FROM (VALUES ('basedagents'),('agentsouk')) AS sources(name) LOOP
    SELECT count(*),
      count(*) FILTER(WHERE status_code=200 AND checked_at IS NOT NULL
                      AND nullif(btrim(coalesce(error,'')),'') IS NULL
                      AND funded_relevant_count IS NOT NULL AND funded_relevant_count>=0
                      AND jsonb_typeof(funded_relevant)='array'),
      min(requested_at),max(requested_at),
      coalesce(jsonb_agg(jsonb_build_object(
        'request_id',request_id,
        'requested_at',requested_at,
        'checked_at',checked_at,
        'http_status',status_code,
        'funded_relevant_count',funded_relevant_count,
        'has_provider_error',nullif(btrim(coalesce(error,'')),'') IS NOT NULL
      ) ORDER BY requested_at DESC),'[]'::jsonb)
    INTO v_total,v_valid,v_oldest,v_latest,v_receipts
    FROM (
      SELECT request_id,requested_at,checked_at,status_code,error,
             funded_relevant_count,funded_relevant
      FROM public.agent_economy_bounty_monitor
      WHERE market=v_market
      ORDER BY requested_at DESC,request_id DESC
      LIMIT 2
    ) recent;
    v_source_ok := (v_total=2 AND v_valid=2
                    AND v_latest>=now()-interval '95 minutes'
                    AND v_oldest>=now()-interval '185 minutes'
                    AND v_latest-v_oldest>=interval '25 minutes');
    v_evidence := v_evidence || jsonb_build_object(v_market,
      jsonb_build_object('source_usable',v_source_ok,
                         'recent_provider_replies',v_receipts,
                         'two_independent_recent_http_200_required',true));
    IF v_source_ok THEN v_allowed:=v_allowed||jsonb_build_array(v_market);
    ELSE v_blocked:=v_blocked||jsonb_build_array(v_market); END IF;
  END LOOP;
  v_state := CASE jsonb_array_length(v_allowed)
               WHEN 0 THEN 'HALTED_NO_TRUSTED_SOURCE'
               WHEN 1 THEN 'DEGRADED_HEALTHY_FALLBACK'
               ELSE 'HEALTHY_MULTI_SOURCE' END;
  SELECT state,allowed_sources INTO v_prior_state,v_prior_allowed
  FROM executive_nexus.market_failover_state
  WHERE route_key='agent_bounty_readonly_discovery' FOR UPDATE;
  v_transition := v_prior_state IS DISTINCT FROM v_state
              OR v_prior_allowed IS DISTINCT FROM v_allowed;
  INSERT INTO executive_nexus.market_failover_state
    (route_key,state,allowed_sources,blocked_sources,evidence,checked_at,last_transition_at)
  VALUES
    ('agent_bounty_readonly_discovery',v_state,v_allowed,v_blocked,v_evidence,now(),now())
  ON CONFLICT(route_key) DO UPDATE SET
    state=excluded.state,allowed_sources=excluded.allowed_sources,
    blocked_sources=excluded.blocked_sources,
    evidence=excluded.evidence,checked_at=now(),
    last_transition_at=CASE WHEN v_transition THEN now()
                          ELSE executive_nexus.market_failover_state.last_transition_at END;
  INSERT INTO executive_nexus.market_failover_checks
    (slot,checked_at,state,allowed_sources,evidence)
  VALUES (v_slot,now(),v_state,v_allowed,v_evidence)
  ON CONFLICT(slot) DO UPDATE SET
    checked_at=excluded.checked_at,state=excluded.state,
    allowed_sources=excluded.allowed_sources,evidence=excluded.evidence;
  IF v_transition THEN
    INSERT INTO executive_nexus.audit_events
      (event_key,owner_role,event_type,result_status,note,evidence_ref)
    VALUES
      ('AEOS2047:MARKET_FAILOVER:'||to_char(v_slot AT TIME ZONE 'UTC','YYYYMMDDHH24'),
       'COO_CFO','SYSTEM_INTERNAL_READONLY_MARKET_SOURCE_SELECTION',
       v_state,
       'Based solely on the last 2 separately timed validated real HTTP 200 provider results per source. '||
       'Internal discovery source selection only; no vendor DNS repair, new external request, funded deal, buyer, wallet or revenue.',
       NULL)
    ON CONFLICT(event_key) DO NOTHING;
  END IF;
  RETURN jsonb_build_object(
    'state',v_state,'allowed_sources',v_allowed,'blocked_sources',v_blocked,
    'provider_receipts',v_evidence,'state_transition',v_transition,
    'external_network_requests',0,'funds_moved',false,'revenue_verified',false,
    'actual_worker_agents_instantiated',0);
END
$function$;
REVOKE ALL ON FUNCTION executive_nexus.run_market_failover_check() FROM PUBLIC,anon,authenticated;

CREATE OR REPLACE VIEW executive_nexus.active_market_discovery_signal
WITH (security_invoker=true) AS
SELECT b.market,
    b.request_id,
    b.requested_at,
    b.checked_at,
    b.status_code,
    b.funded_relevant_count,
    s.state AS source_route_state,
    s.checked_at AS route_checked_at,
    'provider health and synthetic marketplace discovery; neither buyers nor revenue verified'::text AS trust_boundary
   FROM executive_nexus.market_failover_state s
     JOIN agent_economy_bounty_monitor b ON s.route_key = 'agent_bounty_readonly_discovery'::text AND s.allowed_sources ? b.market
  WHERE s.checked_at >= (now() - '01:35:00'::interval) AND b.requested_at >= (now() - '01:35:00'::interval) AND b.checked_at IS NOT NULL AND b.status_code = 200 AND b.funded_relevant_count IS NOT NULL AND b.funded_relevant_count >= 0 AND jsonb_typeof(b.funded_relevant) = 'array'::text AND NULLIF(btrim(COALESCE(b.error, ''::text)), ''::text) IS NULL AND b.request_id = (( SELECT b2.request_id
           FROM agent_economy_bounty_monitor b2
          WHERE b2.market = b.market
          ORDER BY b2.requested_at DESC, b2.request_id DESC
         LIMIT 1));
REVOKE ALL ON executive_nexus.active_market_discovery_signal FROM PUBLIC,anon,authenticated;

-- Active pg_cron job 27: aeos2047-autonomous-market-source-failover-hourly
-- schedule: 16 * * * *
-- command: select executive_nexus.run_market_failover_check();
-- The existing market collector continues independently polling both allowlisted
-- sources hourly; only this internal active-discovery view excludes unhealthy ones.
