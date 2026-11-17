"""Five-qubit quantum-inspired TITAN Ω Q5 empirical falsification checks."""
import copy, math, unittest
from trading import titan_q5_coherence_128 as q5
from trading.edge_lab import BAR_MS

def candles(n=450):
    out=[];p=100.
    for i in range(n):
        v=100+i*.02+math.sin(i/13)*.4
        out.append({"ts":BAR_MS*i,"open":p,
                    "high":max(p,v)+.24,"low":min(p,v)-.24,"close":v})
        p=v
    return out

class Q5(unittest.TestCase):
    def test_goal_and_predeclared_controls(self):
        self.assertEqual((q5.START,q5.TARGET,q5.RUIN),(4.15,9.462,.83))
        self.assertEqual(q5.LEVERAGES,(3.,10.))
        self.assertEqual(len(q5.POLICIES),8)
        self.assertTrue(q5.UNIVERSE.isdisjoint(q5.EXCLUDED))

    def test_unitary_five_qubit_probabilities(self):
        for x in (-3.,-.7,0.,1.1,3.):
            for phase in (0.,.6,1.,1.4):
                p=q5.q5_probability((x,-x/3,x/2,-.2,x/4),phase)
                self.assertGreaterEqual(p,0.)
                self.assertLessEqual(p,1.)

    def test_phase_ablation_actually_changes_output(self):
        f=(1.,-.9,.3,1.1,.6)
        self.assertGreater(abs(q5.q5_probability(f,1.) -
                           q5.q5_probability(f,0.)),1e-6)

    def test_identical_classical_input_and_nonfinite_guard(self):
        self.assertTrue(0<q5.classic_probability((.1,-.2,.3,-.1,.6))<1)
        with self.assertRaises(ValueError):
            q5.q5_probability((float("nan"),0,0,0,0))
        with self.assertRaises(ValueError):
            q5.classic_probability((1,2,3))

    def test_last_uncompleted_candle_cannot_affect_decisions(self):
        rows=candles();first=q5.frozen_stream(rows)
        changed=copy.deepcopy(rows)
        changed[-1]["high"]*=100
        changed[-1]["close"]=changed[-1]["high"]
        self.assertEqual(first,q5.frozen_stream(changed))

    def test_chronological_signals_and_all_policies(self):
        stream=q5.frozen_stream(candles())
        self.assertEqual(set(stream),set(q5.POLICIES))
        self.assertTrue(all(224<=sig[0]<449 for v in stream.values()
                            for sig in v))

    def test_insufficient_dataset_refused(self):
        with self.assertRaises(ValueError):
            q5.evaluate({"AR-USDT-SWAP":candles()},
                        {"AR-USDT-SWAP":{}},{"AR-USDT-SWAP":"sha"})

    def test_no_real_exchange_transactions(self):
        from pathlib import Path
        src=(Path(__file__).parents[1]/"trading/titan_q5_coherence_128.py").read_text()
        self.assertNotIn("OKX_API_KEY",src)
        self.assertNotIn("/api/v5/trade/order",src)
        self.assertIn('"selected_using_training_alone"',src)

if __name__=="__main__":unittest.main()
