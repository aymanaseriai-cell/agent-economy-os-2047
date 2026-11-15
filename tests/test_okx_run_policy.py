import unittest
from trading.okx_run_policy import preflight
from trading.okx_live_executor import ExecutionBlocked, check_mode, MODE_ARM


class WorkflowStopInterlockTests(unittest.TestCase):
    def test_public_research_can_run_while_owner_stop_is_active(self):
        self.assertEqual(
            preflight("research", {"OKX_ENABLE_REAL_TRADING": "NO",
                                   "OKX_STOP_CONTINUOUS": "YES",
                                   "OKX_EXECUTION_MODE": "live"}),
            "RESEARCH_ONLY_PUBLIC_NO_ORDERS")

    def test_validate_is_read_only(self):
        self.assertEqual(preflight("validate", {}),
                         "READ_ONLY_OKX_CONNECTION_CHECK_NO_ORDERS")

    def test_run_with_owner_stop_fails_without_starting_worker(self):
        with self.assertRaisesRegex(ValueError, "OKX_ENABLE_REAL_TRADING=NO"):
            preflight("run", {"OKX_ENABLE_REAL_TRADING": "NO", "OKX_STOP_CONTINUOUS": "YES"})
        with self.assertRaisesRegex(ValueError, "OKX_STOP_CONTINUOUS=YES"):
            preflight("run", {"OKX_ENABLE_REAL_TRADING": "YES", "OKX_STOP_CONTINUOUS": "YES",
                              "OKX_EXECUTION_MODE": "live"})

    def test_both_owner_stop_flags_reported_in_one_failure(self):
        with self.assertRaises(ValueError) as ctx:
            preflight("run", {
                "OKX_EXECUTION_MODE": "live",
                "OKX_ENABLE_REAL_TRADING": "NO",
                "OKX_STOP_CONTINUOUS": "YES",
            })
        self.assertIn("OKX_ENABLE_REAL_TRADING=NO", str(ctx.exception))
        self.assertIn("OKX_STOP_CONTINUOUS=YES", str(ctx.exception))

    def test_live_requires_two_independent_flags(self):
        ok={"OKX_ENABLE_REAL_TRADING":"YES", "OKX_STOP_CONTINUOUS":"NO",
            "OKX_EXECUTION_MODE":"live"}
        self.assertEqual(preflight("run", ok),"LIVE_ARMING_PREFLIGHT_PASSED")
        with self.assertRaisesRegex(ValueError, "OKX_EXECUTION_MODE=live"):
            preflight("run", {**ok, "OKX_EXECUTION_MODE":"dry_run"})

    def test_executor_cannot_bypass_owner_stop_even_if_live_enable_yes(self):
        env={"OKX_EXECUTION_MODE":"live", "OKX_EXECUTION_ARM":MODE_ARM["live"],
             "OKX_ENABLE_REAL_TRADING":"YES", "OKX_STOP_CONTINUOUS":"YES",
             "OKX_API_KEY":"TEST", "OKX_SECRET_KEY":"TEST", "OKX_PASSPHRASE":"TEST"}
        with self.assertRaisesRegex(ExecutionBlocked, "Owner stop flag"):
            check_mode("live", env)

    def test_twenty_five_live_position_slots_require_independent_arming(self):
        env={"OKX_EXECUTION_MODE":"live",
             "OKX_ENABLE_REAL_TRADING":"YES", "OKX_STOP_CONTINUOUS":"NO",
             "OKX_EXECUTION_ARM":MODE_ARM["live"], "OKX_LEVERAGE_MODE":"fixed",
             "OKX_CAPITAL_MODE":"adaptive_guarded",
             "OKX_PORTFOLIO_ARM":"YES", "OKX_MAX_ACTIVE_POSITIONS":"25",
             "OKX_API_KEY":"TEST", "OKX_SECRET_KEY":"TEST",
             "OKX_PASSPHRASE":"TEST"}
        self.assertIsNone(check_mode("live", env))
        with self.assertRaisesRegex(ExecutionBlocked, "between 1 and 25"):
            check_mode("live", {**env, "OKX_MAX_ACTIVE_POSITIONS":"26"})
        with self.assertRaisesRegex(ExecutionBlocked, "portfolio arm"):
            check_mode("live", {**env, "OKX_PORTFOLIO_ARM":"NO"})

    def test_unknown_purpose_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            preflight("trade_anyway", {})


if __name__ == "__main__":
    unittest.main()
