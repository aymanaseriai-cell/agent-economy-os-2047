"""Physically unitary walk, strict causality and no profitable-edge fabrication."""
import math
import unittest
from trading.edge_lab import BAR_MS
from trading.titan_quantum_causal_walk import (
    SYMBOLS,NAMES,wavewalk,generate_signals,train_frequency_match,
    evaluate,MIN_BARS
)


def synthetic(n=460):
    bars=[];last=100.
    for k in range(n):
        p=100+k*.014+.26*math.sin(k/13)
        bars.append({"ts":k*BAR_MS,"open":last,
                     "high":max(last,p)+.4,
                     "low":min(last,p)-.4,"close":p})
        last=p
    return bars


class TestQuantumCausalWalk(unittest.TestCase):
    def test_new_markets_not_from_prior_30(self):
        old=("BTC ETH SOL XRP DOGE SUI LTC ADA AVAX LINK DOT APT "
             "BCH ETC XLM NEAR ATOM UNI TRX FIL AAVE OP ARB INJ "
             "HBAR ICP WLD GALA SAND CRV").split()
        self.assertEqual(len(set(SYMBOLS)),6)
        self.assertFalse(set(SYMBOLS)&{x+"-USDT-SWAP" for x in old})

    def test_unitarity_all_phase_scales_and_market_paths(self):
        for sign in (-1,1):
            prices=[100*math.exp(sign*k*.0001+.003*math.sin(k/4))
                    for k in range(110)]
            for scale in (0.,.75,1.,1.25,2.):
                score,entropy,norm=wavewalk(prices,102,.003,
                                             phase_multiplier=scale)
                self.assertAlmostEqual(norm,1,places=8)
                self.assertTrue(-1-1e-8<=score<=1+1e-8)
                self.assertTrue(0<=entropy<=1+1e-8)

    def test_nontrivial_phase_interference_different_from_zero_phase(self):
        cl=[100*math.exp(k*.0003+.002*math.sin(k/4)) for k in range(110)]
        a,_,_=wavewalk(cl,102,.003,phase_multiplier=1.)
        b,_,_=wavewalk(cl,102,.003,phase_multiplier=0.)
        self.assertGreater(abs(a-b),1e-6)

    def test_no_future_data_in_signals(self):
        a=synthetic()
        sig,diag=generate_signals(a)
        modified=[dict(x) for x in a]
        modified[-1]["close"]=modified[-1]["high"]
        self.assertEqual((sig,diag),generate_signals(modified))
        self.assertEqual(set(sig),set(NAMES))
        self.assertTrue(all(i<len(a)-1 for v in sig.values()
                            for i,side,atr in v))

    def test_training_only_frequency_match_future_independent(self):
        items=[(i,1,1.) for i in range(5,100)]
        quantum=items[:20]
        s1,p1=train_frequency_match(items,quantum,50,"Z-USDT-SWAP")
        # Even if future validation changes, the precomputed training rate is unchanged.
        s2,p2=train_frequency_match(items,quantum+[(500,1,1.)],50,"Z-USDT-SWAP")
        self.assertEqual(p1,p2)
        self.assertEqual(s1,s2)
        self.assertTrue(0<=p1<=1)

    def test_missing_symbol_fails_closed(self):
        with self.assertRaises(ValueError):
            evaluate({SYMBOLS[0]:synthetic()},{})

    def test_short_fabricated_history_fails_closed(self):
        with self.assertRaises(ValueError):
            evaluate({s:synthetic() for s in SYMBOLS},{})

    def test_walk_rejects_unphysical_params(self):
        cl=[100. for _ in range(100)]
        for args in ((3,.003,1.),(50,-.1,1.),(50,.003,4.)):
            with self.assertRaises(ValueError):
                wavewalk(cl,args[0],args[1],phase_multiplier=args[2])


if __name__=="__main__":
    unittest.main()
