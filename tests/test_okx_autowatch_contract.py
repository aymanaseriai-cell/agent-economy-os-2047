"""Contract test: scheduled AutoWatch may monitor but must never trade."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "okx-titan-auto-watch.yml"

class AutoWatchContractTests(unittest.TestCase):
    def test_scheduled_five_minute_readonly_restart(self):
        yaml = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("cron: '*/5 * * * *'", yaml)
        self.assertIn("vars.OKX_AUTOWATCH_ENABLED == 'YES'", yaml)
        self.assertIn("python -m trading.okx_risk_watchdog", yaml)
        self.assertIn("python -m trading.okx_five_second_worker", yaml)

    def test_no_orders_or_credentialed_market_exec(self):
        yaml = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("OKX_EXECUTION_MODE: dry_run", yaml)
        self.assertIn("OKX_ENABLE_REAL_TRADING: 'NO'", yaml)
        self.assertIn("OKX_STOP_CONTINUOUS: 'YES'", yaml)
        self.assertNotIn("--confirm-live", yaml)
        self.assertNotIn("confirm_max_leverage", yaml)
        self.assertNotIn("OKX_EXECUTION_ARM", yaml)
        self.assertNotIn("secrets.OKX_FULL_MARGIN_ARM", yaml)
        self.assertNotIn("gh api --method POST", yaml)
        self.assertNotIn("trading.okx_live_executor", yaml)

if __name__ == "__main__":
    unittest.main()
