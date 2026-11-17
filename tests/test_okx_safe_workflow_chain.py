import unittest
from pathlib import Path

YML=Path(__file__).resolve().parents[1] / '.github/workflows/okx-titan-omega-live-target9.yml'

class TestSafeContinuousWorkflow(unittest.TestCase):
    def test_no_automatic_replay_at_max_exchange_leverage(self):
        s=YML.read_text(encoding='utf-8')
        self.assertIn("vars.OKX_LEVERAGE_MODE != 'exchange_max'",s)
        self.assertIn('Start a new run and explicitly confirm maximum leverage again',s)
        self.assertIn('inputs.confirm_max_leverage != true',s)
        self.assertIn("inputs.confirm_live != true",s)

    def test_read_only_risk_check(self):
        s=YML.read_text(encoding='utf-8')
        self.assertIn("if: inputs.purpose == 'risk_check'",s)
        self.assertIn('run: python -m trading.okx_risk_watchdog',s)

if __name__=='__main__':
    unittest.main()
