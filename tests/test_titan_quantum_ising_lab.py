"""Self-falsification tests: quantum-INSPIRED optimisation, never quantum hardware."""
import math
import unittest
from trading.edge_lab import BAR_MS
from trading.titan_quantum_ising_lab import (
    FAMILIES, COUNT_SELECTED, extra_signals, votes_consensus,
    training_matrix, ising_energy, exact_ground_state, anneal_ising,
    unbiased_null_control,
)


def bars(n=480):
    result=[]
    old=100.0
    for i in range(n):
        close=100+i*.012+math.sin(i/9)*.45
        op=old
        result.append({"ts":i*BAR_MS,"open":op,
                       "high":max(op,close)+.3,
                       "low":min(op,close)-.3,"close":close})
        old=close
    return result


class QuantumInspiredChallenge(unittest.TestCase):
    def test_six_predeclared_features(self):
        self.assertEqual(len(FAMILIES),6)
        self.assertEqual(COUNT_SELECTED,3)

    def test_future_only_final_bar_cannot_change_prior_signal(self):
        sample=bars()
        for name in ("squeeze_release","shock_recovery"):
            expected=extra_signals(sample,name)
            altered=[dict(b) for b in sample]
            altered[-1]["close"]=altered[-1]["high"]
            self.assertEqual(extra_signals(altered,name),expected)

    def test_bitcount_and_invalid_inputs_fail_closed(self):
        mu=[0.0]*6
        cov=[[0.0]*6 for _ in range(6)]
        with self.assertRaises(ValueError):
            ising_energy((1,)*5,mu,cov)
        with self.assertRaises(ValueError):
            ising_energy((0,0,0,0,0,2),mu,cov)

    def test_exact_optimizer_stays_ground_state(self):
        mu=[4,3,2,1,0,-2]
        cov=[[0.0]*6 for _ in range(6)]
        chosen,e=exact_ground_state(mu,cov)
        self.assertEqual(chosen,(0,1,2))
        self.assertEqual(e,-9.0)
        approx,err=anneal_ising(mu,cov,seed=5)
        self.assertEqual(err,e)

    def test_covariance_same_day_alignment(self):
        train={name:{i:(i%3-1)*.001 for i in range(20)}
               for name in FAMILIES}
        mu,cov,days=training_matrix(train)
        self.assertEqual(days,20)
        self.assertEqual(len(mu),6)
        self.assertEqual(len(cov),6)
        self.assertTrue(all(x>=0 for x in (cov[i][i] for i in range(6))))

    def test_conflicting_votes_veto(self):
        rows=[
            [(200,1,1.0)],
            [(200,1,1.0)],
            [(200,-1,1.0)],
        ]+[[] for _ in range(3)]
        self.assertEqual(votes_consensus(rows,(0,1,2)),[])
        rows[2]=[]
        self.assertEqual(votes_consensus(rows,(0,1,2)),[(200,1,1.0)])

    def test_decoy_stays_statistically_unproven(self):
        sample=bars()
        rows=[
            [(250,1,1.0)],
            [(250,1,1.0)],
            [],
        ]+[[] for _ in range(3)]
        b={"BTC-USDT-SWAP":(sample,rows)}
        a=unbiased_null_control(b,(0,1,2),
                                {"BTC-USDT-SWAP":288},actual_mean=0.0,
                                samples=8,seed=5)
        self.assertEqual(a["decoy_trials"],8)
        self.assertTrue(a["controls_are_not_independent_or_proof_of_profit"])

    def test_no_fake_quantum_family(self):
        with self.assertRaises(ValueError):
            extra_signals(bars(),"real_quantum_oracle")


if __name__=="__main__":
    unittest.main()
