-- Agent Economy OS 2047 private sales reply evidence. 2026-11-21.
-- Source snapshot of connected Supabase executive_nexus metadata and safe summary view.
-- No private Gmail message ids, addresses, bodies, or credentials are stored in GitHub.
-- CRM negative dispositions are USER_REQUEST-classified evidence only.
-- Never count a reply, vendor pitch, an AI support answer, or autoack as paid buyer.

CREATE TABLE IF NOT EXISTS executive_nexus.commercial_reply_triage (
  gmail_message_id text PRIMARY KEY CHECK(length(gmail_message_id)>=12),
  organization text NOT NULL,
  reply_day date NOT NULL,
  category text NOT NULL CHECK(category IN
    ('DECLINED','NOT_NEEDED','AUTO_ACK_ONLY','TECHNICAL_INFO_ONLY',
     'PAID_LISTING_NOT_BUYER','RECIPROCAL_DIRECTORY_NOT_BUYER')),
  summary text NOT NULL,
  reply_source text NOT NULL DEFAULT 'GMAIL_READONLY' CHECK(reply_source='GMAIL_READONLY'),
  reviewed_provenance text NOT NULL DEFAULT 'USER_REQUEST' CHECK(reviewed_provenance='USER_REQUEST'),
  willing_to_buy_verified boolean NOT NULL DEFAULT false CHECK(willing_to_buy_verified=false),
  budget_verified boolean NOT NULL DEFAULT false CHECK(budget_verified=false),
  payment_verified boolean NOT NULL DEFAULT false CHECK(payment_verified=false),
  followup_authorized boolean NOT NULL DEFAULT false CHECK(followup_authorized=false),
  classify_only_no_external_reply boolean NOT NULL DEFAULT true CHECK(classify_only_no_external_reply=true),
  observed_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE executive_nexus.commercial_reply_triage ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON executive_nexus.commercial_reply_triage FROM PUBLIC,anon,authenticated;

CREATE OR REPLACE VIEW executive_nexus.commercial_pipeline_evidence
WITH (security_invoker=true)
AS
SELECT category,count(*)::integer as reply_messages,
       count(*) FILTER(WHERE payment_verified)::integer as verified_paid_messages,
       count(*) FILTER(WHERE willing_to_buy_verified)::integer as verified_buy_intent,
       count(*) FILTER(WHERE followup_authorized)::integer as authorized_followups,
       max(reply_day) latest_reply_day,
       'Only selected project replies that were read and classified; not a total CRM funnel or general revenue measure'::text as scope
FROM executive_nexus.commercial_reply_triage
GROUP BY category;
REVOKE ALL ON executive_nexus.commercial_pipeline_evidence FROM PUBLIC,anon,authenticated;

-- Private data was already written only to executive_nexus with RLS and
-- no PUBLIC/anon/authenticated grants. This migration does not seed or export it.
-- The CRO hourly ChatGPT automation consults the summary only to block unwanted
-- follow-ups. New opt-in buyer leads must use independent, separately verified intake.
-- No payments, customer contact, product deployment, or company autonomy claim.
