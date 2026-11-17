"""Physical 3-qubit model and REAL $4.15 discrete-contract safety invariants."""
import math,unittest
from trading.edge_lab import BAR_MS
from trading.titan_quantum_survival_interferometer import (
    EXCLUDED,POLICIES,START,TARGET,RUIN,interferometer,
    classical_probability,affordable_contracts,candidate_stream,
    sim_one,paper_portfolio,signflip_pvalue,evaluate
)


def bars(n=400,step=.018):
    out=[];prev=100.
    for i in range(n):
        p=100+i*step+.33*math.sin(i/9)
        out.append({"ts":i*BAR_MS,"open":prev,
                    "high":max(prev,p)+.3,
                    "low":min(prev,p)-.3,"close":p})
        prev=p
    return out


def spec(coin="TEST",*,ctval="0.001",minsz="1",lot="1"):
    return {"instId":coin+"-USDT-SWAP","ctType":"linear",
            "ctValCcy":coin,"state":"live","ctVal":ctval,
            "minSz":minsz,"lotSz":lot}


class MicroQuantumAudit(unittest.TestCase):
    def test_three_qubit_norm_and_phases(self):
        for i in range(120):
            v=(math.sin(i/8),math.cos(i/7),math.tanh(i/9-5))
            for phase in (0,.7,1,1.3,2):
                p,n=interferometer(v,phase=phase)
                self.assertAlmostEqual(n,1,places=8)
                self.assertGreaterEqual(p,0)
                self.assertLessEqual(p,1)

    def test_quantum_model_not_phase_independent(self):
        choices=[(.5,-1.3,1.2),(1.2,-.4,-.6),(.7,.4,-.8)]
        differences=[abs(interferometer(v,phase=1)[0]-
                         interferometer(v,phase=0)[0]) for v in choices]
        self.assertGreater(max(differences),1e-6)

    def test_classical_symmetric_distribution(self):
        self.assertAlmostEqual(classical_probability((0.,0.,0.)),.5)
        self.assertTrue(0<=classical_probability((1.,2.,3.))<=1)

    def test_minimum_exact_contract_quantization(self):
        x,n=affordable_contracts(spec(),100,.8,START,3)
        self.assertGreater(x,0)
        self.assertEqual(x,round(x))
        self.assertLessEqual(n/3,START*.4+1e-8)
        x,n=affordable_contracts(spec(ctval="100",minsz="1"),
                                  100,.8,START,3)
        self.assertEqual(x,0)

    def test_fail_closed_invalid_micro_account(self):
        self.assertEqual(affordable_contracts(
            spec(),100,.8,RUIN,3),(0.,0.))
        self.assertEqual(affordable_contracts(
            spec(),100,.8,START,100),(0.,0.))
        self.assertEqual(affordable_contracts(
            spec(minsz="0"),100,.8,START,3),(0.,0.))

    def test_signal_causality(self):
        a=bars()
        x=candidate_stream(a)
        mod=[dict(z) for z in a]
        mod[-1]["close"]=mod[-1]["high"]
        self.assertEqual(x,candidate_stream(mod))
        self.assertEqual(set(x),set(POLICIES))
        self.assertTrue(all(i<len(a)-1 for items in x.values()
                            for i,side,atr,strength in items))

    def test_simulation_cannot_spend_more_than_equity(self):
        a=bars(350)
        signal=(250,1,.8,.4)
        x=sim_one(a,signal,spec(),equity=START,leverage=10,
                  fee=.0005,slip=.0003,end=350)
        self.assertIsNotNone(x)
        self.assertGreaterEqual(x["equity_after"],0)
        self.assertLessEqual(x["equity_after"],START+10)
        self.assertGreaterEqual(x["min_contract_quantity"],1)

    def test_portfolio_initializes_4_15_and_never_fabricates_pnl(self):
        a=bars(350)
        sym="TEST-USDT-SWAP"
        report=paper_portfolio({sym:a},{sym:spec()},
            {sym:{k:[] for k in POLICIES}},start=224,end=350,
            policy=POLICIES[0],leverage=3)
        self.assertEqual(report["trades"],0)
        self.assertEqual(report["ending_usdt"],START)
        self.assertFalse(report["reached_8_30"])

    def test_cross_market_alignment_fails_closed(self):
        a=bars(6000)
        sym="TEST-USDT-SWAP"
        with self.assertRaises(ValueError):
            evaluate({sym:a},{sym:spec()})

    def test_few_daily_results_cannot_claim_significance(self):
        self.assertIsNone(signflip_pvalue([]))

if __name__=="__main__":
    unittest.main()
