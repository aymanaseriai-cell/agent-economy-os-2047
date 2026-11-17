"""New 64% QSI paper milestone, exposure reduction, no lookahead/no orders."""
import unittest
from trading import titan_qsi_plus64_profitlock as model


class QSI64Test(unittest.TestCase):
    def test_target_is_64_percent_not_32_or_100(self):
        self.assertAlmostEqual(model.TARGET64,6.806,places=6)
        self.assertAlmostEqual(model.TARGET32,5.478,places=6)

    def test_risk_reduces_only_after_REALIZED_32(self):
        self.assertEqual(model.effective_leverage(4.15,10,"after32_reduce5"),10)
        self.assertEqual(model.effective_leverage(5.47799,10,"after32_reduce5"),10)
        self.assertEqual(model.effective_leverage(5.478,10,"after32_reduce5"),5)
        self.assertEqual(model.effective_leverage(5.478,10,"after32_reduce3"),3)
        self.assertEqual(model.effective_leverage(6.9,10,"after32_reduce3"),3)
        self.assertEqual(model.effective_leverage(4.15,3,"after32_reduce5"),3)

    def test_fixed_leverage_is_exact_control(self):
        for lev in model.LEVERAGES:
            for eq in (4.15,5.478,6.806):
                self.assertEqual(model.effective_leverage(eq,lev,"fixed"),lev)

    def test_reject_adaptive_non_precommitted_modes(self):
        with self.assertRaises(ValueError):
            model.effective_leverage(6.9,10,"increase_to_50x")

    def test_no_trade_no_fabricated_profit(self):
        market={"TEST-USDT-SWAP":[{"ts":i*900000,
                    "open":1.,"high":1.1,"low":.9,"close":1.} for i in range(8)]}
        p=model.book_with_gate(market,{"TEST-USDT-SWAP":{}},
            {"TEST-USDT-SWAP":{"quantum_phase_robust":[]}},
            policy="quantum_phase_robust",leverage=10,start=1,end=8,
            fee=.0005,slip=.0003,mode="after32_reduce3")
        self.assertEqual(p["trades"],0)
        self.assertEqual(p["ending_usdt"],4.15)
        self.assertFalse(p["reached_and_locked_64_at_close"])

    def test_failed_lot_attempts_are_not_called_filled_trades(self):
        market={"TEST-USDT-SWAP":[{"ts":i*900000,"open":1.,
                "high":2.,"low":.5,"close":1.} for i in range(10)]}
        def no_fill(bars,signal,spec,*,equity,leverage,fee,slip,end):
            return None
        p=model.book_with_gate(market,{"TEST-USDT-SWAP":{}},
            {"TEST-USDT-SWAP":{"quantum_phase_robust":[(1,1,.3,.4)]}},
            policy="quantum_phase_robust",leverage=10,start=1,end=10,
            fee=.0005,slip=.0003,mode="after32_reduce3",executor=no_fill)
        self.assertEqual(p["trades"],0)
        self.assertEqual(p["paper_trades_after_32_stage"],0)
        self.assertEqual(p["max_paper_leverage_used"],0)

    def test_64_is_only_confirmed_after_actual_closed_equity(self):
        market={"TEST-USDT-SWAP":[{"ts":i*900000,"open":1.,"high":20.,
                "low":.01,"close":1.} for i in range(10)]}
        counter=[]
        def fake(bars,signal,spec,*,equity,leverage,fee,slip,end):
            counter.append(leverage)
            return {"equity_after":5.5 if len(counter)==1 else 6.85,
                    "exit_i":signal[0]+1,"entry_fee_usdt":.001,
                    "exit_fee_usdt":.001}
        p=model.book_with_gate(market,{"TEST-USDT-SWAP":{}},
            {"TEST-USDT-SWAP":{"quantum_phase_robust":[
                (1,1,.3,.4),(3,1,.3,.4),(5,1,.3,.4)]}},
            policy="quantum_phase_robust",leverage=10,start=1,end=10,
            fee=.0005,slip=.0003,mode="after32_reduce3",executor=fake)
        self.assertEqual(counter,[10,3])
        self.assertEqual(p["trades"],2)
        self.assertTrue(p["reached_and_locked_64_at_close"])
        self.assertAlmostEqual(p["ending_usdt"],6.85,places=6)

if __name__=="__main__":
    unittest.main()
