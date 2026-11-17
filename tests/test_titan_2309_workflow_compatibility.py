import unittest
from pathlib import Path
class Restored2309Compatibility(unittest.TestCase):
    def test_dynamic_compatibility_without_automatic_consent(self):
        x=(Path(__file__).resolve().parents[1]/".github/workflows/okx-titan-omega-live-target9.yml").read_text()
        self.assertEqual(x.count("OKX_LEVERAGE_MODE: 'dynamic'"),2)
        self.assertIn("inputs.confirm_live != true",x)
        self.assertIn("secrets.OKX_DYNAMIC_LEVERAGE_ARM",x)
        self.assertIn("vars.OKX_STOP_CONTINUOUS",x)
        self.assertIn("vars.OKX_ENABLE_REAL_TRADING",x)
if __name__ == "__main__":
    unittest.main()
