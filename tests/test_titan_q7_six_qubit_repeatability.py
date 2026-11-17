"""Q7 pre-committed six-qubit coherence repeatability tests."""
import copy, math, unittest
from trading import titan_q7_six_qubit_repeatability as q7
from trading.edge_lab import BAR_MS

def synthetic(n=16*66,trend=.01):
    x=[];previous=100.
    for i in range(n):
        price=100+i*trend+.2*math.sin(i/29)
        x.append({"ts":i*BAR_MS,"open":previous,
                  "high":max(previous,price)+.4,
                  "low":min(previous,price)-.4,"close":price})
        previous=price
    return x

class Q7(unittest.TestCase):
    def test_mathematically_unitary_six_qubit(self):
        for t in (-3.,-1.,0.,1.,3.):
            for phase in (0.,.7,1.,1.3):
                v=q7.quantum_probability((t,t/2,t/3,-t/4,t/5,t/6),phase)
                self.assertTrue(0<=v<=1)
    def test_phase_ablation_changes_born_probability(self):
        x=(1.,-.4,.9,-.7,1.2,-.3)
        self.assertGreater(abs(q7.quantum_probability(x,1.)-
                               q7.quantum_probability(x,0.)),1e-7)
    def test_input_validation(self):
        with self.assertRaises(ValueError):
            q7.quantum_probability((1,2,3))
        with self.assertRaises(ValueError):
            q7.quantum_probability((float("nan"),1,1,1,1,1))
        with self.assertRaises(ValueError):
            q7.classical_probability((1,2,3))
    def test_last_unfinished_4h_candle_not_read(self):
        b=synthetic()
        h=q7.four_hour_bars(b)
        extra=copy.deepcopy(b)+[{"ts":b[-1]["ts"]+BAR_MS,"open":100,
                               "high":100000,"low":.001,"close":100000}]
        self.assertEqual(q7.four_hour_bars(extra),h)
    def test_four_disjoint_independent_walk_forward_windows(self):
        part=q7.splits(17279)
        self.assertEqual(len(q7.PARTS),4)
        self.assertEqual(part["train"][1],part["holdout_1"][0])
        for i in range(3):
            self.assertEqual(part[q7.PARTS[i]][1],
                             part[q7.PARTS[i+1]][0])
        self.assertEqual(part["combined_holdouts"],
                         (part["holdout_1"][0],part["holdout_4"][1]))
    def test_no_prior_baskets_in_new_study_universe(self):
        self.assertTrue(q7.UNIVERSE.isdisjoint(q7.PREVIOUS))
        self.assertEqual((q7.START,q7.GOAL),(4.15,9.462))
    def test_expected_all_policy_signals(self):
        row=synthetic()
        group={"ACH-USDT-SWAP":row,"FET-USDT-SWAP":row,
               "KAVA-USDT-SWAP":row,"SUSHI-USDT-SWAP":row,
               "YFI-USDT-SWAP":row,"QTUM-USDT-SWAP":row}
        s=q7.signals(group)
        self.assertEqual(set(s),set(group))
        self.assertEqual(set(next(iter(s.values()))),set(q7.POLICIES))
    def test_quantization_enforces_minimum_and_zero_fantasy_fills(self):
        s={"instId":"ACH-USDT-SWAP","state":"live","ctValCcy":"ACH",
           "ctVal":"1","lotSz":"1","minSz":"100000"}
        self.assertEqual(q7.contracts(s,4.15,.2,.01,10),(0.,0.))
    def test_missing_data_fails_closed(self):
        with self.assertRaises(ValueError):
            q7.evaluate({}, {}, {})
        with self.assertRaises(ValueError):
            q7.splits(5000)
    def test_no_real_orders(self):
        from pathlib import Path
        code=(Path(__file__).parents[1]/
              "trading/titan_q7_six_qubit_repeatability.py").read_text()
        self.assertNotIn("/api/v5/trade/order",code)
        self.assertNotIn("OKX_API_KEY",code)
        self.assertIn('"selected_validated_128_four_times"',code)

if __name__=="__main__":unittest.main()
