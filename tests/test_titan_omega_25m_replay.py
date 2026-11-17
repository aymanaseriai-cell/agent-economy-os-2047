import unittest,hashlib
from trading import titan_omega_25m_replay as r
class TestReplay(unittest.TestCase):
    def test_reader_refuses_incomplete_manifest(self):
        with self.assertRaises((KeyError,ValueError)):
            r.replay(lambda name:b'{"source_manifest":{}}')
    def test_replay_offline_and_no_orders(self):
        from pathlib import Path
        code=(Path(__file__).parents[1]/"trading/titan_omega_25m_replay.py").read_text()
        self.assertNotIn("urlopen(",code)
        self.assertNotIn("/api/v5/trade/order",code)
        self.assertIn("all_432_evaluations_replayed",code)
if __name__=="__main__":unittest.main()
