"""QSI +128: closed-PnL milestones, strict chronological no-trade fallback."""
import unittest
from trading import titan_qsi_plus128_paper as test


def market():
    return {"TEST-USDT-SWAP":[{"ts":i*900000,"open":100.,
         "high":200.,"low":50.,"close":100.} for i in range(15)]}


def votes(xs):
    return {s:{"quantum_phase_robust":xs} for s in market()}


def fake_seq(endings):
    iterator=iter(endings)
    seen=[]
    def step(bars,signal,spec,*,equity,leverage,fee,slip,end):
        seen.append((float(equity),float(leverage)))
        return {"equity_after":next(iterator),"exit_i":signal[0]+1,
                "entry_fee_usdt":.001,"exit_fee_usdt":.001,
                "status":"target"}
    return step,seen


class Plus128Paper(unittest.TestCase):
    def test_exact_128_target(self):
        self.assertEqual(test.TARGET128,9.462)
        self.assertEqual(test.TARGET32,5.478)
        self.assertEqual(test.TARGET64,6.806)

    def test_predeclared_gate_modes(self):
        self.assertEqual(test.leverage_for_realized_equity(5.477,"reduce5_after32"),10)
        self.assertEqual(test.leverage_for_realized_equity(5.478,"reduce5_after32"),5)
        self.assertEqual(test.leverage_for_realized_equity(6.8059,"reduce3_after64"),10)
        self.assertEqual(test.leverage_for_realized_equity(6.806,"reduce3_after64"),3)
        self.assertEqual(test.leverage_for_realized_equity(5.48,"reduce5_after32_reduce3_after64"),5)
        self.assertEqual(test.leverage_for_realized_equity(6.81,"reduce5_after32_reduce3_after64"),3)

    def test_reject_new_unfrozen_mode(self):
        with self.assertRaises(ValueError):
            test.leverage_for_realized_equity(100,"jackpot_100x")

    def test_one_position_and_stop_only_AFTER_realized_goal(self):
        sig=[(1,1,1,.7),(3,1,1,.7),(5,1,1,.7),(7,1,1,.7)]
        step,seen=fake_seq([5.6,6.9,9.54,14.])
        out=test.paper_lock128(market(),{"TEST-USDT-SWAP":{}},
            votes(sig),policy="quantum_phase_robust",
            mode="reduce5_after32_reduce3_after64",start=1,end=15,
            fee=.0005,slip=.0003,trade_func=step)
        self.assertEqual(len(seen),3)
        self.assertEqual([x[1] for x in seen],[10,5,3])
        self.assertTrue(out["plus128_goal_closed_equity_reached"])
        self.assertEqual(out["trades"],3)
        self.assertEqual(out["end_usdt"],9.54)

    def test_no_intra_high_false_positive(self):
        step,seen=fake_seq([6.,7.])
        out=test.paper_lock128(market(),{"TEST-USDT-SWAP":{}},
            votes([(1,1,1,.7),(3,1,1,.7)]),
            policy="quantum_phase_robust",mode="fixed10",start=1,end=15,
            fee=.0005,slip=.0003,trade_func=step)
        self.assertFalse(out["plus128_goal_closed_equity_reached"])
        self.assertEqual(out["end_usdt"],7.)

    def test_zero_signals_cannot_hit_target(self):
        out=test.paper_lock128(market(),{"TEST-USDT-SWAP":{}},votes([]),
            policy="quantum_phase_robust",mode="fixed3",
            start=1,end=15,fee=.0005,slip=.0003)
        self.assertEqual(out["end_usdt"],4.15)
        self.assertEqual(out["trades"],0)
        self.assertFalse(out["plus128_goal_closed_equity_reached"])

    def test_unfillable_contract_is_not_a_trade(self):
        def reject(*args,**kwargs):return None
        out=test.paper_lock128(market(),{"TEST-USDT-SWAP":{}},
            votes([(1,1,1,.7)]),policy="quantum_phase_robust",
            mode="fixed3",start=1,end=15,fee=.0005,
            slip=.0003,trade_func=reject)
        self.assertEqual(out["trades"],0)
        self.assertEqual(out["end_usdt"],4.15)

if __name__=="__main__":
    unittest.main()
