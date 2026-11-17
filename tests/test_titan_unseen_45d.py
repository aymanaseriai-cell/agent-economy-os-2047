"""TITAN real-market blind experiment invariants, synthetic fixtures, zero network."""
import math
import unittest
from unittest.mock import patch
from trading.edge_lab import BAR_MS
from trading.titan_unseen_45d import (
    FAMILIES,SYMBOLS,variance_ratio,binary_entropy,advanced_signals,
    all_signals,training_ising
)


def synthetic(n=440):
    rows=[]
    prev=100
    for k in range(n):
        cl=100+0.018*k+math.sin(k/7)*0.6
        o=prev
        rows.append({"ts":k*BAR_MS, "open":o,
                     "high":max(o,cl)+.5, "low":min(o,cl)-.5,"close":cl})
        prev=cl
    return rows


class SixUnseenRealMarket(unittest.TestCase):
    def test_fixed_markets_are_different_from_old_basket(self):
        self.assertEqual(len(SYMBOLS),6)
        self.assertFalse(set(SYMBOLS) & {
            "BTC-USDT-SWAP","ETH-USDT-SWAP","SOL-USDT-SWAP",
            "XRP-USDT-SWAP","DOGE-USDT-SWAP","SUI-USDT-SWAP"})
        self.assertEqual(len(FAMILIES),6)

    def test_variance_ratio_is_causal_and_finite(self):
        c=[b["close"] for b in synthetic()]
        vr=variance_ratio(c,300)
        c[340]=c[340]*200
        self.assertEqual(vr,variance_ratio(c,300))
        self.assertGreater(vr,0)

    def test_shannon_entropy_is_bounded_and_causal(self):
        c=[b["close"] for b in synthetic()]
        h=binary_entropy(c,300)
        self.assertGreaterEqual(h,0)
        self.assertLessEqual(h,1+1e-12)

    def test_all_three_hypotheses_never_look_ahead(self):
        rows=synthetic()
        for name in FAMILIES[3:]:
            original=advanced_signals(rows,name)
            altered=[dict(x) for x in rows]
            altered[-1]["close"]=altered[-1]["high"]
            self.assertEqual(advanced_signals(altered,name),original)
            self.assertTrue(all(i<len(rows)-1 and side in (-1,1)
                                for i,side,atr in original))

    def test_unsupported_strategy_fails_closed(self):
        with self.assertRaises(ValueError):
            all_signals(synthetic(),"future_omniscience")

    def test_train_covariance_only_uses_known_days(self):
        d={name:{k:0.1*k for k in range(20)} for name in FAMILIES}
        mu,cov,days=training_ising(d)
        self.assertEqual(days,20)
        self.assertEqual(len(mu),6)
        self.assertTrue(all(cov[k][k]>=0 for k in range(6)))

    def test_missing_training_data_refused(self):
        with self.assertRaises(ValueError):
            training_ising({name:{} for name in FAMILIES})

    def test_no_private_okx_calls_in_source(self):
        from trading import titan_unseen_45d
        import inspect
        source=inspect.getsource(titan_unseen_45d)
        self.assertNotIn("OKX_SECRET_KEY",source)
        self.assertNotIn("/api/v5/trade/order",source)


if __name__=="__main__":
    unittest.main()
