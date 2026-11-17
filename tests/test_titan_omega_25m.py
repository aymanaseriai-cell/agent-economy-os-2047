"""OMEGA SINGULARITY 25M: deterministic checks, NOT synthetic profit evidence."""
import copy,math,unittest
from trading import titan_omega_25m_families as f
from trading import titan_omega_25m_market as m
from trading import titan_omega_25m_engine as e
from trading.edge_lab import BAR_MS

def fake(n=16*100):
    p=100.;b=[]
    for i in range(n):
        x=100+i*.013+.2*math.sin(i/12)
        b.append({"ts":i*BAR_MS,"open":p,"close":x,
                  "high":max(p,x)+.3,"low":min(p,x)-.3,
                  "vol_quote":1000+i%50*30})
        p=x
    return b

class Omega(unittest.TestCase):
    def test_exact_target_no_false_percent_conversion(self):
        self.assertEqual(e.START,4.15)
        self.assertEqual(e.TARGET_PCT,25_000_000.)
        self.assertAlmostEqual(e.TARGET,1_037_504.15)
    def test_families_20_plus_classical_baseline(self):
        self.assertEqual(len(f.MODELS),21)
        self.assertEqual(len(f.UNAVAILABLE),3)
        self.assertEqual(len(f.ACTIVE),18)
        self.assertTrue(set(f.UNAVAILABLE).isdisjoint(f.ACTIVE))
    def test_unitary_four_qubit(self):
        x=(.8,-.6,.9,-.2,.1,.1,-.4,.5,.1,-.3)
        for phase in (0.,.65,1.,1.35):
            result=f.quantum_probability(x,phase)
            self.assertTrue(0<=result<=1)
        with self.assertRaises(ValueError):
            f.quantum_probability((float("nan"),)*10)
    def test_original_market_volume_from_exact_okx_column(self):
        r=["900000","99","103","98","100","4","4","1560","1"]
        self.assertEqual(m.decode(r)["vol_quote"],1560.)
        self.assertIsNone(m.decode(r[:-1]+["0"]))
        with self.assertRaises(ValueError):
            m.decode(r[:7]+["NaN","1"])
    def test_last_partial_4h_candle_does_not_change_features(self):
        b=fake()
        plus=copy.deepcopy(b)+[{"ts":b[-1]["ts"]+BAR_MS,
            "open":1,"high":10000,"low":.1,"close":90,"vol_quote":1e8}]
        self.assertEqual(m.aggregate(b),m.aggregate(plus))
    def test_training_models_are_deterministic_and_sealed(self):
        x=(.1,-.2,.3,.2,.4,.5,.1,0.,.3,.2)
        train=[(x,.005,"FET-USDT-SWAP",0)]*202
        fitted=f.fit(train)
        self.assertEqual(fitted["gene"],f.fit(train)["gene"])
        self.assertEqual(len(fitted["gene"]),10)
        self.assertEqual(set(f.score(x,"FET-USDT-SWAP",fitted)),set(f.ACTIVE))
    def test_purged_90d_fitting_and_holdouts(self):
        w=e.windows(17279)
        self.assertLess(w["fit"][1],w["development"][0])
        self.assertLess(w["development"][1],w["final_1"][0])
        self.assertLess(w["final_1"][1],w["final_2"][0])
        self.assertLess(w["final_2"][1],w["final_3"][0])
    def test_lot_min_qty_enforced_on_small_equity(self):
        spec={"instId":"FET-USDT-SWAP","state":"live","ctValCcy":"FET",
              "ctVal":"1000","minSz":"1","lotSz":"1"}
        self.assertEqual(e.affordable(spec,4.15,100.,1.,10.),(0.,0.))
    def test_stops_no_lookahead_and_portfolio_ruin(self):
        b=fake()
        spec={"instId":"FET-USDT-SWAP","state":"live","ctValCcy":"FET",
              "ctVal":"1","minSz":".01","lotSz":".01"}
        sig=(16*73-1,1,.5,.9)
        t=e.simulate(b,sig,spec,[],4.15,3.,.0005,.0003,len(b))
        self.assertTrue(t is None or (t["entry_ts"]==b[sig[0]+1]["ts"] and
                                      t["equity_after"]>=0))
    def test_training_winner_selection_only_development(self):
        a={"train_model":{"fit":{"stress":{"trades":5,"net_return_pct":2}},
                           "development":{"stress":{"net_return_pct":3,
                               "max_closed_drawdown_pct":4,"ruin":False},
                               "ordinary":{"net_return_pct":3}},
                           "final_1":{"stress":{"net_return_pct":-99}}}}
        winner,qualified=e.training_selection(a)
        self.assertEqual(winner,"train_model")
        self.assertEqual(qualified,["train_model"])
    def test_no_real_order_endpoint_or_private_keys(self):
        from pathlib import Path
        root=Path(__file__).parents[1]/"trading"
        for name in ("titan_omega_25m_families.py","titan_omega_25m_market.py",
                     "titan_omega_25m_engine.py"):
            src=(root/name).read_text()
            self.assertNotIn("/api/v5/trade/order",src)
            self.assertNotIn("OKX_API_KEY",src)
    def test_sanity_missing_market_panel_is_refused(self):
        with self.assertRaises(ValueError):
            e.study({}, {}, {}, {})

if __name__=="__main__":unittest.main()
