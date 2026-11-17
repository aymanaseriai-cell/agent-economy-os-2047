"""Independent falsification of Infinite Frontier Gen2 mathematical claims."""
import copy,math,unittest
from trading import titan_frontier_v2_models as m
from trading import titan_frontier_v2_research as r
from trading.edge_lab import BAR_MS

class FrontierTests(unittest.TestCase):
    def test_target_and_true_holdouts(self):
        self.assertEqual((r.START,r.TARGET),(4.15,1_037_504.15))
        s=r.windows(17279)
        self.assertLess(s["fit"][1],s["development"][0])
        self.assertLess(s["development"][1],s["final_1"][0])
        self.assertLess(s["final_1"][1],s["final_2"][0])
        self.assertLess(s["final_2"][1],s["final_3"][0])
    def test_true_koopman_ridge_gaussian_solver(self):
        x=[(1.,float(i),float(i*i%3),.1,0.,0.,0.) for i in range(80)]
        y=[.02+.03*i for i in range(80)]
        w=m.solve_ridge(x,y,ridge=.01)
        self.assertEqual(len(w),7)
        self.assertTrue(all(math.isfinite(v) for v in w))
        self.assertAlmostEqual(sum(a*b for a,b in zip(w,x[-1])),y[-1],delta=.05)
    def test_kalman_updates_only_from_observed_past(self):
        a=m.BayesianKalman(.8,.02)
        b=m.BayesianKalman(.8,.02)
        past=[.01,-.02,.005,.013,-.011]
        for ret in past:self.assertEqual(a.update(ret),b.update(ret))
        b.update(1.)
        self.assertNotAlmostEqual(a.mu,b.mu)
    def test_explicit_duration_semi_markov_normalizes(self):
        h=m.DurationHSMM(.02)
        for v in [.01]*10+[-.02]*10:
            mean,up=h.update(v)
            self.assertTrue(0<=up<=1)
            self.assertAlmostEqual(sum(h.probs.values()),1.,places=10)
            self.assertTrue(all(1<=d<=48 for _,d in h.probs))
    def test_bayesian_online_changepoint_normalized(self):
        b=m.BOCPD(.02)
        for x in [.003]*20+[.1]+[-.005]*20:
            p=b.update(x)
            self.assertTrue(0<=p<=1)
            self.assertAlmostEqual(sum(b.weights),1.,places=10)
    def test_finite_sample_conformal_quantile_and_no_final_labels(self):
        self.assertEqual(m.conformal_threshold(list(range(100)),.1),90)
        with self.assertRaises(ValueError):
            m.conformal_threshold(list(range(12)),.1)
    def test_robust_risk_gate_rejects_weak_edge(self):
        self.assertEqual(m.robust_edge(.002,.01,.002,1.25),0.)
        self.assertGreater(m.robust_edge(.1,.01,.002,1.25),0.)
    def test_quantum_inspired_annealer_not_assumed_better_than_exact(self):
        utilities=[.25,.9,.45,.1,.05,.37,.13]
        q=m.softmax_anneal(utilities)
        exact=m.exact_enumeration(utilities)
        self.assertTrue(0<=q<7)
        self.assertEqual(exact,1)
        self.assertLessEqual(utilities[q],utilities[exact])
        for x in (-1,0,1):
            self.assertTrue(0<=m.softmax_anneal([.25]+[x]*6)<7)
    def test_frozen_public_crypto_research_cohort(self):
        self.assertTrue(r.COHORT_EXCLUDE.isdisjoint(
            r.market.POOL-r.COHORT_EXCLUDE))
        self.assertEqual(len(r.POLICIES),10)
        self.assertEqual(r.CANDIDATE_COUNT,20)
        self.assertEqual(set(r.COSTS),{"ordinary","stress","extreme"})
    def test_fail_closed_without_real_history(self):
        with self.assertRaises(ValueError):
            r.evaluate({}, {}, {}, {})
    def test_closed_pnl_no_trade_without_real_minlot(self):
        data=[{"ts":i*BAR_MS,"open":100.,"high":101.,"low":99.,
               "close":100.,"vol_quote":1000.} for i in range(100)]
        name="FLOW-USDT-SWAP"
        spec={"instId":name,"state":"live","ctValCcy":"FLOW",
              "minSz":"1","ctVal":"1000","lotSz":"1"}
        out=r.conservative_paper({name:data},{name:spec},{name:[]},
                                {name:[(20,1,1.,.5)]},10,15,90,.001,.001)
        self.assertEqual(out["trades"],0)
        self.assertGreater(out["rejected"]["insufficient_lot"],0)
        self.assertEqual(out["net_return_pct"],0)
    def test_conservative_quote_volume_cap_refuses_oversized(self):
        data=[{"ts":i*BAR_MS,"open":10.,"high":10.5,"low":9.5,
               "close":10.,"vol_quote":1.} for i in range(100)]
        name="FLOW-USDT-SWAP"
        spec={"instId":name,"state":"live","ctValCcy":"FLOW",
              "minSz":".01","ctVal":"1","lotSz":".01"}
        out=r.conservative_paper({name:data},{name:spec},{name:[]},
                                {name:[(20,1,.2,.5)]},3,15,90,.001,.001)
        self.assertEqual(out["trades"],0)
        self.assertGreater(out["rejected"]["insufficient_quote_volume"],0)
    def test_price_history_sha_and_no_private_order_actions(self):
        from pathlib import Path
        root=Path(__file__).parents[1]/"trading"
        for file in ("titan_frontier_v2_models.py","titan_frontier_v2_research.py"):
            text=(root/file).read_text()
            self.assertNotIn("/api/v5/trade/order",text)
            self.assertNotIn("OKX_API_KEY",text)
        self.assertEqual(r.digest(b"ABC"),
                         __import__("hashlib").sha256(b"ABC").hexdigest())

if __name__=="__main__":unittest.main()
