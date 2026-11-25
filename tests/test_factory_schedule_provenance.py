"""Review-only SQL provenance guard; tests cannot alter a live database."""
import unittest
from pathlib import Path

SQL = (Path(__file__).resolve().parents[1] / "infra" / "supabase" /
       "factory_schedule_provenance_review_20261121.sql")

class FactoryScheduleProvenanceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = SQL.read_text(encoding="utf8")
        cls.body = cls.sql.split("AS $function$", 1)[1].split("END\n$function$;",1)[0]

    def test_exact_cron_receipts_required_for_both_modes(self):
        for num in (27,28):
            self.assertIn(f"r.jobid={num} AND r.status='succeeded'",self.body)
        self.assertEqual(self.body.count("r.end_time IS NOT NULL"),2)
        self.assertEqual(self.body.count("c.checked_at>=r.start_time AND c.checked_at<=r.end_time"),2)
        self.assertEqual(self.body.count("c.execution_origin='UNVERIFIED'"),2)
        self.assertEqual(self.body.count("c.slot=pg_catalog.date_trunc('hour',r.start_time)"),2)

    def test_do_not_assert_untrusted_market_source_health(self):
        self.assertIn("c.actual_outbound_http_requests=0",self.body)
        self.assertIn("c.customer_contacts=0 AND c.payment_actions=0",self.body)
        self.assertIn("c.allowed_sources='[\"basedagents\"]'::jsonb",self.body)
        self.assertEqual(self.body.count("http_status}'='200'"),2)
        self.assertIn("IS DISTINCT FROM c.evidence",self.body)

    def test_no_sales_or_revenue_episode_fabrication(self):
        self.assertNotIn("INSERT INTO executive_nexus.autonomy_episode_log",self.body)
        self.assertNotIn("INSERT INTO public.agent_enterprise_inquiries",self.body)
        self.assertNotIn("cron.schedule(",self.body)
        self.assertIn("'financial_actions',0",self.body)
        self.assertIn("'eligible_for_new_autonomy_episodes',false",self.body)

    def test_restricted_and_nonproduction(self):
        self.assertIn("NOT DEPLOYED",self.sql)
        self.assertIn("pg_catalog.pg_try_advisory_xact_lock",self.body)
        self.assertIn("REVOKE ALL ON FUNCTION executive_nexus.reconcile_factory_schedule_provenance()",self.sql)

if __name__ == "__main__":
    unittest.main()
