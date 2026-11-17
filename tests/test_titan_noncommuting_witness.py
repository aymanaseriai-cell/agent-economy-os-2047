"""QOPW physical quantum-instrument and causal evaluation invariants."""
import math
import unittest
from trading.edge_lab import BAR_MS
from trading.titan_noncommuting_witness import (
    SYMBOLS,POLICIES,witness,physical_povm_bloch,create_signals,
    completed_pressure,run_study,
)


def synthetic(n=500):
    bars=[];prev=100.
    for i in range(n):
        cl=100+i*.011+.2*math.sin(i/11)
        bars.append({"ts":i*BAR_MS,"open":prev,
                     "high":max(cl,prev)+.35,
                     "low":min(cl,prev)-.35,"close":cl})
        prev=cl
    return bars


class QuantumOrderParadox(unittest.TestCase):
    def test_fixed_markets_unused_in_prior_three_baskets(self):
        self.assertEqual(len(set(SYMBOLS)),6)
        old=("BTC ETH SOL XRP DOGE SUI LTC ADA AVAX LINK DOT APT "
             "BCH ETC XLM NEAR ATOM UNI TRX FIL AAVE OP ARB INJ").split()
        self.assertFalse(set(SYMBOLS)&{v+"-USDT-SWAP" for v in old})

    def test_every_outcome_preserves_density_positivity(self):
        r=(.1,.2,.3)
        for idx in range(72):
            r=physical_povm_bloch(
                r,axis=idx%3,outcome=1 if idx%2 else -1,
                strength=.45)
            self.assertLessEqual(sum(z*z for z in r),1+1e-10)
        with self.assertRaises(ValueError):
            physical_povm_bloch((2.,0.,0.),axis=0,outcome=1,strength=.5)

    def test_noncommutativity_is_genuine(self):
        d=witness((.13,0.,.17),1,1)
        self.assertGreater(d["order_gap"],1e-5)
        self.assertNotEqual(
            d["actual_evolution_after_trend_then_impulse"][2],
            d["counterfactual_after_impulse_then_trend"][2])

    def test_invalid_outcome_or_axis_is_refused(self):
        for kwargs in ({"axis":5,"outcome":1,"strength":.5},
                       {"axis":2,"outcome":0,"strength":.5},
                       {"axis":2,"outcome":1,"strength":1.1}):
            with self.assertRaises(ValueError):
                physical_povm_bloch((0.,0.,0.),**kwargs)

    def test_physical_measurement_is_equivalent_to_bloch_bayes(self):
        # Start in maximally mixed rho. Condition on Z+.
        z=physical_povm_bloch((0.,0.,0.),axis=2,outcome=1,strength=.62)
        self.assertAlmostEqual(z[2],.62)
        # Nonselective outcomes produce the old mixed state.
        minus=physical_povm_bloch((0.,0.,0.),axis=2,outcome=-1,strength=.62)
        self.assertAlmostEqual((z[2]+minus[2])/2,0)

    def test_causality_corrupt_unfinished_bar(self):
        bars=synthetic()
        original,info=create_signals(bars)
        nextbars=[dict(v) for v in bars]
        nextbars[-1]["close"]=nextbars[-1]["high"]
        changed,details=create_signals(nextbars)
        self.assertEqual(original,changed)
        self.assertEqual(info,details)
        self.assertEqual(set(original),set(POLICIES))
        self.assertTrue(all(i<len(bars)-1 for rows in original.values()
                            for i,side,atr in rows))

    def test_public_candle_pressure_is_bounded_and_causal(self):
        bars=synthetic()
        p=completed_pressure(bars,250)
        self.assertTrue(-1<=p<=1)
        bars[270]["close"]*=5
        self.assertEqual(p,completed_pressure(bars,250))

    def test_rejects_missing_markets_and_short_history(self):
        with self.assertRaises(ValueError):
            run_study({SYMBOLS[0]:synthetic()},{})
        with self.assertRaises(ValueError):
            run_study({s:synthetic() for s in SYMBOLS},{})


if __name__=="__main__":
    unittest.main()
