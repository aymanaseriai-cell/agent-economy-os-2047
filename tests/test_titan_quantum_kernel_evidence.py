"""Check physical quantum feature map and training-label no-lookahead."""
import math
import unittest
from trading.edge_lab import BAR_MS
from trading.titan_quantum_kernel_evidence import (
    SYMBOLS,POLICIES,qmap,fidelity,rbfsim,precompute,signals_for_market,
    stressed_label,calibration_group,estimate,evaluate,HOLD_BARS
)


def synthetic(n=680):
    data=[];previous=100.
    for i in range(n):
        p=100+i*.015+.28*math.sin(i/11)
        data.append({"ts":i*BAR_MS,"open":previous,
                     "high":max(p,previous)+.35,
                     "low":min(p,previous)-.35,"close":p})
        previous=p
    return data


class QuantumKernelTests(unittest.TestCase):
    def test_new_unseen_basket(self):
        old=("BTC ETH SOL XRP DOGE SUI LTC ADA AVAX LINK DOT APT "
             "BCH ETC XLM NEAR ATOM UNI TRX FIL AAVE OP ARB INJ "
             "HBAR ICP WLD GALA SAND CRV PEPE SHIB PENDLE TIA SEI JUP").split()
        self.assertEqual(len(SYMBOLS),6)
        self.assertFalse(set(SYMBOLS) & {s+"-USDT-SWAP" for s in old})

    def test_unitary_map_norm_and_fidelity_bounds(self):
        for x in range(60):
            feat=(math.tanh(x/10-3),math.tanh(x/13-2),
                  math.sin(x/9),math.cos(x/17))
            state=qmap(feat)
            self.assertAlmostEqual(sum(abs(a)**2 for a in state),1,places=9)
            self.assertAlmostEqual(fidelity(state,state),1,places=9)
            self.assertTrue(0<=fidelity(state,qmap((0,0,0,0)))<=1)

    def test_actual_entangling_map_nonseparable_case(self):
        state=qmap((.8,-.3,.5,.7))
        self.assertGreater(abs(state[0]*state[3]-state[1]*state[2]),1e-5)

    def test_distinct_features_change_quantum_kernel(self):
        a=qmap((.8,0,.2,0))
        b=qmap((-.8,0,-.2,0))
        self.assertLess(fidelity(a,b),.999)
        self.assertLess(rbfsim((.8,0,.2,0),(-.8,0,-.2,0)),1)

    def test_unfinished_candle_never_affects_signals(self):
        bars=synthetic()
        sig,detail=signals_for_market(bars)
        alter=[dict(z) for z in bars]
        alter[-1]["close"]=alter[-1]["high"]
        self.assertEqual((sig,detail),signals_for_market(alter))
        self.assertEqual(set(sig),set(POLICIES))
        self.assertTrue(all(i<len(bars)-1 for rows in sig.values()
                            for i,_,_ in rows))

    def test_training_labels_never_cross_fit_boundary(self):
        bars=synthetic()
        pre=precompute(bars)
        fit=int(len(bars)*.45)
        for family in ("trend","reversion"):
            group=calibration_group(bars,pre,fit,family)
            allowed=[x for x in pre if x[1]==family
                     and x[0]+HOLD_BARS+1<fit]
            self.assertLessEqual(len(group),len(allowed))

    def test_missing_data_and_short_data_fail(self):
        with self.assertRaises(ValueError):
            evaluate({SYMBOLS[0]:synthetic()},{})
        with self.assertRaises(ValueError):
            evaluate({s:synthetic() for s in SYMBOLS},{})

    def test_empty_calibration_means_no_trade(self):
        item=(0,"trend",1,1.,(0.,0.,0.,0.),qmap((0.,0.,0.,0.)))
        allowed,lower,eff=estimate(item,[],quantum=True)
        self.assertFalse(allowed)

if __name__=="__main__":
    unittest.main()
