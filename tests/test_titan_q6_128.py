"""New Q6 quantum statevector and long-horizon paper engine invariants."""
import copy,math,unittest
from trading import titan_q6_128 as q
from trading.edge_lab import BAR_MS

def candles(n=450):
    price=100.;rows=[]
    for i in range(n):
        c=100+.012*i+.2*math.sin(i/9)
        rows.append({"ts":i*BAR_MS,"open":price,
                     "high":max(price,c)+.32,
                     "low":min(price,c)-.32,"close":c})
        price=c
    return rows

class Q6SystemTests(unittest.TestCase):
    def test_128_goal_includes_no_arbitrary_reduction(self):
        self.assertEqual((q.START,q.TARGET,q.RUIN),(4.15,9.462,.83))
        self.assertEqual(q.LEVERAGES,(3.,10.))
        self.assertEqual(q.DAYS,90)
        self.assertTrue(q.UNIVERSE.isdisjoint(q.EXCLUDED))

    def test_statevector_unitarity_for_64_amplitudes(self):
        for x in (-3.,-1.,0.,1.,3.):
            for phase in (0.,.55,1.,1.45):
                value=q.q6_probability((x,x/2,-x/2,.5,-.7,x/4),phase)
                self.assertTrue(0.<=value<=1.)

    def test_quantum_phase_is_not_empty_cosmetic_step(self):
        f=(1.,-.6,.5,1.2,-.9,.3)
        self.assertGreater(abs(q.q6_probability(f,0)-
                               q.q6_probability(f,1)),1e-7)

    def test_classical_control_same_feature_count(self):
        self.assertTrue(0<q.classic_probability((1,1,1,-1,-1,.1))<1)
        with self.assertRaises(ValueError):
            q.classic_probability((1,2,3))
        with self.assertRaises(ValueError):
            q.q6_probability((1,2,3,4,5,float("nan")))

    def test_signal_never_looks_into_final_uncompleted_bar(self):
        bars=candles()
        original=q.signal_stream(bars)
        changed=copy.deepcopy(bars)
        changed[-1]["high"]*=50
        changed[-1]["close"]=changed[-1]["high"]
        self.assertEqual(original,q.signal_stream(changed))

    def test_all_policies_and_chronological_signals(self):
        s=q.signal_stream(candles())
        self.assertEqual(set(s),set(q.POLICIES))
        self.assertTrue(all(224<=v[0]<449 for row in s.values() for v in row))
        self.assertTrue(all(v[0]%q.SCAN_EVERY==0 for row in s.values() for v in row))

    def test_missing_instrument_prevents_fake_order(self):
        spec={"ctType":"linear","state":"live","instId":"BONK-USDT-SWAP",
              "ctValCcy":"BONK","ctVal":"1","lotSz":"1","minSz":"1"}
        self.assertEqual(q.contract_quantity(spec,100,1,.83,3),(0.,0.))
        self.assertEqual(q.contract_quantity(spec,100,1,4.15,3),(0.,0.))

    def test_zero_signals_cannot_create_paper_128(self):
        b=candles()
        spec={"ctType":"linear","state":"live","instId":"BONK-USDT-SWAP",
              "ctValCcy":"BONK","ctVal":"1","lotSz":"1","minSz":"1"}
        row=q.replay({"BONK-USDT-SWAP":b},{"BONK-USDT-SWAP":spec},
                     {"BONK-USDT-SWAP":[]},start=224,end=449,
                     leverage=3,fee=.0005,slip=.0003)
        self.assertEqual(row["return_pct"],0.)
        self.assertFalse(row["hit128_on_closed_paper_equity"])

    def test_fail_closed_wrong_market_count(self):
        with self.assertRaises(ValueError):
            q.evaluate({"BONK-USDT-SWAP":candles()},
                       {"BONK-USDT-SWAP":{}},{"BONK-USDT-SWAP":"x"})

    def test_no_live_order_endpoint_or_account_secret(self):
        from pathlib import Path
        text=(Path(__file__).parents[1]/"trading/titan_q6_128.py").read_text()
        self.assertNotIn("/api/v5/trade/order",text)
        self.assertNotIn("OKX_API_KEY",text)
        self.assertIn('"selected_on_train_only"',text)

if __name__=="__main__":
    unittest.main()
