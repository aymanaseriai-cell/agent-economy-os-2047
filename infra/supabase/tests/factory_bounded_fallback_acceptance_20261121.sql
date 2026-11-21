-- Non-mutating Postgres acceptance tests. The checked SQL function is immutable and
-- returns a review-only verdict. These tests never create provider records, trade,
-- contact customers, make network requests or move money.
WITH cases(label, state, allowed, blocked,age,samples,good,latest,oldest,gap,incident_open,expected) AS (
 VALUES
 ('good_provider_evidence','DEGRADED_HEALTHY_FALLBACK','["basedagents"]'::jsonb,'["agentsouk"]'::jsonb,interval '20 minutes',2,2,interval '30 minutes',interval '90 minutes',interval '60 minutes',true,'VERIFIED_BOUNDED_FALLBACK'),
 ('one_provider_sample','DEGRADED_HEALTHY_FALLBACK','["basedagents"]'::jsonb,'["agentsouk"]'::jsonb,interval '20 minutes',1,1,interval '30 minutes',interval '90 minutes',interval '60 minutes',true,'NOT_ACCEPTABLE'),
 ('stale_provider_samples','DEGRADED_HEALTHY_FALLBACK','["basedagents"]'::jsonb,'["agentsouk"]'::jsonb,interval '20 minutes',2,2,interval '180 minutes',interval '220 minutes',interval '40 minutes',true,'NOT_ACCEPTABLE'),
 ('all_sources_bad','HALTED_NO_TRUSTED_SOURCE','[]'::jsonb,'["basedagents","agentsouk"]'::jsonb,interval '20 minutes',2,2,interval '30 minutes',interval '90 minutes',interval '60 minutes',true,'NOT_ACCEPTABLE'),
 ('source_unblocked_incorrectly','DEGRADED_HEALTHY_FALLBACK','["basedagents"]'::jsonb,'[]'::jsonb,interval '20 minutes',2,2,interval '30 minutes',interval '90 minutes',interval '60 minutes',true,'NOT_ACCEPTABLE'),
 ('route_stale','DEGRADED_HEALTHY_FALLBACK','["basedagents"]'::jsonb,'["agentsouk"]'::jsonb,interval '120 minutes',2,2,interval '30 minutes',interval '90 minutes',interval '60 minutes',true,'NOT_ACCEPTABLE'),
 ('incident_resolved','DEGRADED_HEALTHY_FALLBACK','["basedagents"]'::jsonb,'["agentsouk"]'::jsonb,interval '20 minutes',2,2,interval '30 minutes',interval '90 minutes',interval '60 minutes',false,'NOT_ACCEPTABLE'),
 ('zero_spacing','DEGRADED_HEALTHY_FALLBACK','["basedagents"]'::jsonb,'["agentsouk"]'::jsonb,interval '20 minutes',2,2,interval '30 minutes',interval '30 minutes',interval '0 minutes',true,'NOT_ACCEPTABLE'),
 ('bad_sample','DEGRADED_HEALTHY_FALLBACK','["basedagents"]'::jsonb,'["agentsouk"]'::jsonb,interval '20 minutes',2,1,interval '30 minutes',interval '90 minutes',interval '60 minutes',true,'NOT_ACCEPTABLE'),
 ('negative_route_age','DEGRADED_HEALTHY_FALLBACK','["basedagents"]'::jsonb,'["agentsouk"]'::jsonb,interval '-1 seconds',2,2,interval '30 minutes',interval '90 minutes',interval '60 minutes',true,'NOT_ACCEPTABLE')
)
SELECT label,
  executive_nexus.fallback_acceptance_verdict(state,allowed,blocked,age,samples,good,latest,oldest,gap,incident_open) AS actual,
  expected,
  executive_nexus.fallback_acceptance_verdict(state,allowed,blocked,age,samples,good,latest,oldest,gap,incident_open)=expected AS passed
FROM cases;
-- Diagnostic only: DOES NOT CHANGE any task, incident, or provider state.
SELECT executive_nexus.complete_bounded_failover_review(true) AS provider_readiness_dry_run;
