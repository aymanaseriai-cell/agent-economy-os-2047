"""Quantum time-arrow circuit and bounded public micro-account research checks."""
import math,unittest
from trading.edge_lab import BAR_MS
from trading.titan_quantum_time_reversal import (
    PREVIOUS_QSI, POLICIES, arrow, circuit, shocks, candidate_stream,
    CRYPTO_ONLY_UNIVERSE, evaluate, MAX_MARKETS
)


def sample(n=440):
    prev=100.
    arr=[]
    for k in range(n):
        close=100+.01*k+.25*math.sin(k/7)
        arr.append({"ts":k*BAR_MS,"open":prev,
                    "high":max(prev,close)+.3,"low":min(prev,close)-.3,
                    "close":close})
        prev=close
    return arr


class TimeReversalTests(unittest.TestCase):
    def test_unitary_for_wide_shocks(self):
        for v in range(30):
            seq=tuple(math.sin(v/5+j*.7) for j in range(8))
            for coupling in (0.,.75,1.,1.25,1.5):
                z,norm=circuit(seq,coupling=coupling)
                self.assertAlmostEqual(norm,1,places=8)
                self.assertLessEqual(abs(z),1+1e-8)

    def test_palindrome_time_arrow_is_zero(self):
        seq=(.1,-.8,.7,.4,.4,.7,-.8,.1)
        self.assertAlmostEqual(arrow(seq),0,places=10)

    def test_noncommutativity_yields_genuine_order_asymmetry(self):
        seq=(.2,-1.,.7,.4,-.2,.8,-.7,.3)
        self.assertGreater(abs(arrow(seq)),1e-6)

    def test_classical_ablation_has_same_causal_inputs(self):
        arr=sample()
        a=candidate_stream(arr)
        b=[dict(x) for x in arr]
        b[-1]["close"]=b[-1]["high"]
        self.assertEqual(a,candidate_stream(b))
        self.assertEqual(set(a),set(POLICIES))
        self.assertTrue(all(i<len(arr)-1 for rows in a.values()
                            for i,_,_,_ in rows))

    def test_shocks_exclude_future(self):
        cls=[100+.1*i for i in range(320)]
        a=shocks(cls,250,.02)
        cls[280]*=1000
        self.assertEqual(a,shocks(cls,250,.02))
        self.assertEqual(len(a),8)

    def test_prior_baskets_excluded(self):
        self.assertTrue(PREVIOUS_QSI.isdisjoint(CRYPTO_ONLY_UNIVERSE-PREVIOUS_QSI))
        self.assertEqual(MAX_MARKETS,6)

    def test_invalid_circuit_fails(self):
        with self.assertRaises(ValueError):
            circuit((.1,.2))
        with self.assertRaises(ValueError):
            circuit((0.,)*8,coupling=10.)

    def test_missing_market_rejected_without_results(self):
        with self.assertRaises(ValueError):
            evaluate({"TEST-USDT-SWAP":sample()},{})

if __name__=="__main__":
    unittest.main()
