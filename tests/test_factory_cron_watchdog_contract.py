"""Fail-closed contract tests for the private SQL factory cron watchdog.

These inspect review-only source invariants; they do not deploy SQL or fake a
provider-backed incident recovery.
"""
import unittest
from pathlib import Path

SQL_PATH = (Path(__file__).resolve().parents[1] / "infra" / "supabase" /
            "factory_cron_watchdog_20261121.sql")


class FactoryCronWatchdogContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = SQL_PATH.read_text(encoding="utf-8")

    def test_inflight_or_unknown_run_status_prevents_replay(self):
        self.assertIn("p_last_run IS NOT NULL", self.sql)
        self.assertIn("p_last_status IS NULL OR p_last_status NOT IN ('succeeded','failed')",
                      self.sql)
        self.assertIn("THEN 'RUN_STATUS_UNCERTAIN_NO_REPLAY'", self.sql)
        self.assertIn("'RUN_STATUS_UNCERTAIN_NO_REPLAY'", self.sql)

    def test_early_observation_rechecks_only_preliminary_state(self):
        self.assertIn("ON CONFLICT(slot,jobid) DO UPDATE", self.sql)
        self.assertIn("IN ('WAIT_EXPECTED_RUN','WARMUP_NOT_DUE')", self.sql)
        self.assertIn("factory_cron_watchdog_checks.retry_attempts=0", self.sql)
        self.assertIn("IS DISTINCT FROM excluded.verdict", self.sql)

    def test_one_attempt_per_hour_and_terminal_verdicts_stay_terminal(self):
        self.assertIn("PRIMARY KEY(slot,jobid)", self.sql)
        self.assertIn("v_inserted=1 AND v_decision='REPLAY_ELIGIBLE'", self.sql)
        self.assertIn("CASE WHEN v_decision='REPLAY_ELIGIBLE' THEN 1 ELSE 0 END",
                      self.sql)
        self.assertNotIn("ON CONFLICT(slot,jobid) DO NOTHING", self.sql)
        self.assertIn("'another_automatic_retry_in_same_hour',false", self.sql)

    def test_private_scope_and_source_not_misreported_as_deployed(self):
        self.assertIn("THIS safety correction is REVIEW-ONLY", self.sql)
        self.assertIn("execution_origin='UNVERIFIED'", self.sql)
        self.assertIn("pg_catalog.pg_try_advisory_xact_lock", self.sql)
        self.assertIn("REVOKE ALL ON FUNCTION executive_nexus.run_factory_cron_watchdog()",self.sql)
        self.assertIn("'financial_actions',0", self.sql)
        self.assertIn("'full_company_autonomy_verified',false", self.sql)
        self.assertIn("DROP CONSTRAINT IF EXISTS factory_cron_watchdog_checks_verdict_check",
                      self.sql)
        self.assertIn("ADD CONSTRAINT factory_cron_watchdog_checks_verdict_check",self.sql)


if __name__ == "__main__":
    unittest.main()
