"""No-order tests: user-specified 8.30 USDT equity target for TITAN Ω.

The legacy module/workflow retain their Target9 identifiers for compatibility,
but the effective equity threshold and close-arming string are 8.30 USDT.
"""
import unittest
from decimal import Decimal
from pathlib import Path

from tests.test_okx_target9_guard import Fake, pos, run
from trading.okx_live_executor import ExecutionBlocked
from trading.okx_target9_guard import TARGET, ARM, check_target, usdt_equity


class Equity830GoalTests(unittest.TestCase):
    def test_exact_target_is_830_not_900(self):
        self.assertEqual(TARGET, Decimal("8.30"))
        self.assertEqual(ARM, "I_AUTHORIZE_CLOSE_USDT_SWAPS_AT_8_30_USDT")
        for amount in ("4.15", "8.29"):
            with self.subTest(eq=amount):
                fake=Fake(eq=amount, positions=[pos()])
                self.assertEqual(run(fake), "BELOW_TARGET")
                self.assertEqual(fake.posts, [])

    def test_exact_830_with_no_positions_marks_success_without_orders(self):
        fake=Fake(eq="8.30")
        self.assertEqual(run(fake), "TARGET9_FLAT")
        self.assertEqual(fake.posts, [])

    def test_830_above_threshold_without_consent_never_writes(self):
        fake=Fake(eq="8.30", positions=[pos()])
        with self.assertRaises(ExecutionBlocked):
            run(fake, armed=False)
        self.assertEqual(fake.posts, [])

    def test_post_close_fee_shortfall_not_called_target_success(self):
        class CloseFees(Fake):
            def request(self, method, path, *, params=None, body=None, auth=True):
                result=super().request(method, path, params=params, body=body, auth=auth)
                if method == "POST" and path == "/api/v5/trade/close-position":
                    self.eq="8.27"
                return result
        fake=CloseFees(eq="8.31",positions=[pos()])
        with self.assertRaisesRegex(ExecutionBlocked, "fell below 8.30"):
            run(fake)
        self.assertFalse(fake.positions)

    def test_close_above_target_and_verify_realized_balance(self):
        fake=Fake(eq="8.50", positions=[pos()])
        self.assertEqual(run(fake), "TARGET9_FLAT")
        self.assertGreaterEqual(usdt_equity(fake), TARGET)

    def test_workflow_refuses_old_arm_at_eight_thirty(self):
        content=(Path(__file__).resolve().parents[1]/
                 ".github/workflows/okx-titan-omega-live-target9.yml").read_text()
        self.assertIn("I_AUTHORIZE_CLOSE_USDT_SWAPS_AT_8_30_USDT",content)
        self.assertNotIn("I_AUTHORIZE_CLOSE_USDT_SWAPS_AT_9_USDT",content)
        self.assertIn("inputs.confirm_live != true",content)


if __name__ == "__main__":
    unittest.main()
