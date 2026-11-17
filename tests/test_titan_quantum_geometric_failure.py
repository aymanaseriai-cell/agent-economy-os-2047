"""Quantum fidelity geometry, no lookahead, train-only turnover controls."""
import math, unittest
from trading.edge_lab import BAR_MS
from trading.titan_quantum_geometric_failure import (
    quantum_market_state, quantum_surprise, fidelity, classical_surprise,
    signals,_train_match,POLICIES,evaluate,EARLIER_QTRW
)


def fake_bars(n=420):
    a=[];last=100.
    for k in range(n):
        p=100+.006*k+.26*math.sin(k/9)
        a.append({"ts":k*BAR_MS,"open":last,
                  "high":max(last,p)+.34,
                  "low":min(last,p)-.34,"close":p})
        last=p
    return a


class QuantumGeometricTests(unittest.TestCase):
    def test_quantum_unitary_norm_and_fidelity_bounds(self):
        for i in range(80):
            x=(math.sin(i/8),math.cos(i/7),math.tanh(i/9-3),math.sin(i/5))
            for coupling in (0,.75,1,1.25,1.5):
                state=quantum_market_state(x,coupling=coupling)
                self.assertAlmostEqual(sum(abs(z)**2 for z in state),1,places=8)
                self.assertAlmostEqual(fidelity(state,state),1,places=8)
                self.assertTrue(0<=fidelity(state,quantum_market_state((0,0,0,0)))<=1)

    def test_geometric_surprise_zero_for_identical_contexts(self):
        x=(.2,.1,-.4,.3)
        pts=[x,x,x,x]
        self.assertAlmostEqual(quantum_surprise(pts),0,places=9)
        self.assertAlmostEqual(classical_surprise(pts),0,places=9)

    def test_entanglement_phase_changes_distances(self):
        points=[(.3,.2,-1.,.7),(-.5,.2,.7,-.2),
                (.7,-.1,-.7,.9),(-.6,.5,.2,-.4)]
        self.assertGreater(abs(quantum_surprise(points,coupling=1)-
                               quantum_surprise(points,coupling=0)),1e-6)

    def test_no_future_candle_data_read(self):
        bars=fake_bars()
        result=signals(bars,"TEST-USDT-SWAP",int(len(bars)*.6))
        later=[dict(x) for x in bars]
        later[-1]["close"]=later[-1]["high"]
        self.assertEqual(result,signals(later,"TEST-USDT-SWAP",int(len(bars)*.6)))
        self.assertEqual(set(result[0]),set(POLICIES))
        self.assertTrue(all(idx<len(bars)-1 for group in result[0].values()
                            for idx,side,atr,confidence in group))

    def test_matching_fraction_frozen_on_training_only(self):
        classical=[(i,1,1.,.3) for i in range(30,150)]
        quantum=classical[::2]
        a,fa=_train_match(classical,quantum,80,"AAA-USDT-SWAP")
        b,fb=_train_match(classical,quantum+[(900,1,1.,.3)],80,"AAA-USDT-SWAP")
        self.assertEqual((a,fa),(b,fb))

    def test_excluded_previously_researched_crypto(self):
        self.assertTrue({"CHZ","BONK","GRT","STX","WIF"}<=EARLIER_QTRW)

    def test_missing_real_markets_fails_closed(self):
        with self.assertRaises(ValueError):
            evaluate({"AAA-USDT-SWAP":fake_bars()},{})

    def test_invalid_quantum_features_rejected(self):
        for a in ((0,0,0),(0,0,0,float("nan"))):
            with self.assertRaises(ValueError):
                quantum_market_state(a)
        with self.assertRaises(ValueError):
            quantum_market_state((0,0,0,0),coupling=2.)

if __name__=="__main__":
    unittest.main()
