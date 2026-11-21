-- Agent Economy OS 2047 — independent-evidence accounting, not percent inflation.
-- Exact pg_get_viewdef() snapshot from deployed PRIVATE Supabase database, 21 Nov 2026.
-- No Data API access to anon/authenticated; this review-only file has NO auto-deploy wiring.
CREATE OR REPLACE VIEW executive_nexus.factory_autonomy_evidence_14d
WITH (security_invoker=true)
AS
WITH observed AS (
         SELECT autonomy_episode_log.episode_key,
            autonomy_episode_log.owner_role,
            autonomy_episode_log.trigger_type,
            autonomy_episode_log.trigger_ref,
            autonomy_episode_log.triggered_at,
            autonomy_episode_log.finished_at,
            autonomy_episode_log.result_status,
            autonomy_episode_log.eligible_routine,
            autonomy_episode_log.is_synthetic,
            autonomy_episode_log.human_interventions,
            autonomy_episode_log.evidence_ref,
            autonomy_episode_log.provider_verified,
            autonomy_episode_log.controls_passed,
            autonomy_episode_log.policy_violation,
            autonomy_episode_log.recorded_at,
            autonomy_episode_log.note
           FROM executive_nexus.autonomy_episode_log
          WHERE autonomy_episode_log.triggered_at >= (now() - '14 days'::interval) AND autonomy_episode_log.eligible_routine IS TRUE AND autonomy_episode_log.is_synthetic IS FALSE
        ), verified AS (
         SELECT observed.episode_key,
            observed.owner_role,
            observed.trigger_type,
            observed.trigger_ref,
            observed.triggered_at,
            observed.finished_at,
            observed.result_status,
            observed.eligible_routine,
            observed.is_synthetic,
            observed.human_interventions,
            observed.evidence_ref,
            observed.provider_verified,
            observed.controls_passed,
            observed.policy_violation,
            observed.recorded_at,
            observed.note
           FROM observed
          WHERE observed.result_status = 'VERIFIED'::text AND observed.trigger_type = 'SCHEDULED'::text AND observed.human_interventions = 0 AND observed.provider_verified IS TRUE AND observed.controls_passed IS TRUE AND observed.policy_violation IS FALSE AND observed.evidence_ref IS NOT NULL
        ), aggregate_observed AS (
         SELECT count(*)::integer AS eligible_routine_episodes,
            min(observed.triggered_at) AS first_eligible_at,
            max(observed.triggered_at) AS latest_eligible_at
           FROM observed
        ), aggregate_verified AS (
         SELECT count(*)::integer AS recorded_verified_episodes,
            count(DISTINCT verified.evidence_ref)::integer AS distinct_provider_proof_references,
            count(DISTINCT ROW(verified.owner_role, verified.evidence_ref))::integer AS distinct_role_proof_pairs,
            count(DISTINCT verified.owner_role)::integer AS executive_roles_with_verified_episodes,
            count(DISTINCT (verified.triggered_at AT TIME ZONE 'UTC'::text)::date)::integer AS distinct_verified_utc_days,
            min(verified.triggered_at) AS earliest_verified_at,
            max(verified.triggered_at) AS latest_verified_at
           FROM verified
        )
 SELECT o.eligible_routine_episodes,
    v.recorded_verified_episodes,
    v.distinct_provider_proof_references,
    v.distinct_role_proof_pairs,
    v.executive_roles_with_verified_episodes,
    v.distinct_verified_utc_days,
    o.first_eligible_at,
    o.latest_eligible_at,
        CASE
            WHEN o.first_eligible_at IS NOT NULL AND o.first_eligible_at <= (now() - '14 days'::interval) AND v.executive_roles_with_verified_episodes = 4 AND v.distinct_provider_proof_references >= 4 THEN 'INDEPENDENT_FULL_COMPANY_VALIDATION_STILL_REQUIRED'::text
            ELSE 'NOT_VERIFIED_FULL_COMPANY_AUTONOMY'::text
        END AS full_company_autonomy_verdict,
    'A repeated receipt is one distinct provider proof; successful CI rereads are not separate worker execution, customer acceptance, repaired incidents or settled revenue.'::text AS measurement_boundary
   FROM aggregate_observed o
     CROSS JOIN aggregate_verified v;
REVOKE ALL ON executive_nexus.factory_autonomy_evidence_14d FROM PUBLIC,anon,authenticated;
-- This view does not prove 100% company autonomy or count repeated CI reads as new delivery.
