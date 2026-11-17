"""Realized-only 32% QSI target lock must never use future favorable highs."""
import unittest
from trading.titan_qsi_target32_lock_test import target_book,TARGET32


def demo(markets=None):
    arr=[{"ts":i*900000,"open":100.,"high":101.,
          "low":99.,"close":100.} for i in range(8)]
    return {"TEST-USDT-SWAP":arr}


class QSI32TargetTests(unittest.TestCase):
    def _trade(self,ending):
        def simulate(bars,signal,spec,*,equity,leverage,fee,slip,end):
            return {"equity_after":ending,"exit_i":signal[0]+1,
                    "entry_fee_usdt":.001,"exit_fee_usdt":.001}
        return simulate

    def test_stops_immediately_after_confirmed_realized_32(self):
        v={s:{"quantum_phase_robust":[(1,1,.3,.7),(3,1,.3,.7)]}
           for s in demo()}
        p=target_book(demo(),{"TEST-USDT-SWAP":{}},v,
            policy="quantum_phase_robust",leverage=3,start=1,end=8,
            fee=.0005,slip=.0003,one_trade=self._trade(5.5))
        self.assertEqual(p["trades"],1)
        self.assertTrue(p["reached_and_locked_32_at_close"])
        self.assertGreaterEqual(p["ending_usdt"],TARGET32)

    def test_cannot_call_unrealized_intrabar_high_a_target(self):
        v={s:{"quantum_phase_robust":[(1,1,.3,.7)]} for s in demo()}
        p=target_book(demo(),{"TEST-USDT-SWAP":{}},v,
            policy="quantum_phase_robust",leverage=3,start=1,end=8,
            fee=.0005,slip=.0003,one_trade=self._trade(4.9))
        self.assertFalse(p["reached_and_locked_32_at_close"])

    def test_no_trade_is_zero_return(self):
        v={"TEST-USDT-SWAP":{"quantum_phase_robust":[]}}
        p=target_book(demo(),{"TEST-USDT-SWAP":{}},v,
            policy="quantum_phase_robust",leverage=3,start=1,end=8,
            fee=.0005,slip=.0003)
        self.assertEqual(p["trades"],0)
        self.assertEqual(p["ending_usdt"],4.15)

    def test_invalid_target_rejected(self):
        with self.assertRaises(ValueError):
            target_book(demo(),{},{"TEST-USDT-SWAP":{}},
                policy="quantum_phase_robust",leverage=3,start=1,end=8,
                fee=.0005,slip=.0003,goal=4.15)


if __name__=="__main__":
    unittest.main()
