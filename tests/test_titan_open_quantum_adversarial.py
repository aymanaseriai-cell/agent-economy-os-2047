"""Density-matrix validity, lookahead rejection, adversarial stress, WAIT."""
import copy
import hashlib
import json
import math
import unittest

from trading.edge_lab import BAR_MS
from trading.titan_open_quantum_adversarial import (
    SYMBOLS, NAMES, WARMUP, clamp, density_step, density_mat,
    historical_eight_bar_log_returns, minimax_expected_log, make_survival_signals
)


def synthetic(n=440, drift=.015):
    a=[];last=100
    for i in range(n):
        c=100+i*drift+.3*math.sin(i/7)
        op=last
        a.append({"ts":i*BAR_MS,"open":op,
                  "high":max(op,c)+.3,"low":min(op,c)-.3,"close":c})
        last=c
    return a


class OpenQuantumAdversarialTests(unittest.TestCase):
    def test_symbol_list_is_new_and_fixed(self):
        self.assertEqual(len(SYMBOLS),6)
        self.assertFalse(set(SYMBOLS)&{
            "BTC-USDT-SWAP","ETH-USDT-SWAP","SOL-USDT-SWAP",
            "XRP-USDT-SWAP","DOGE-USDT-SWAP","SUI-USDT-SWAP",
            "LTC-USDT-SWAP","ADA-USDT-SWAP","AVAX-USDT-SWAP",
            "LINK-USDT-SWAP","DOT-USDT-SWAP","APT-USDT-SWAP"})

    def test_density_is_hermitian_unit_trace_positive(self):
        st=(0.,0.,0.)
        for i in range(120):
            st=density_step(st,rotation=.3*math.sin(i),
                            dephasing=(i%9)/10,reset=.15,
                            bias=.9*math.cos(i/4))
            rho=density_mat(st)
            self.assertAlmostEqual((rho[0][0]+rho[1][1]).real,1,places=11)
            self.assertEqual(rho[0][1],rho[1][0].conjugate())
            self.assertGreaterEqual((rho[0][0]*rho[1][1]-
                                     rho[0][1]*rho[1][0]).real,-1e-10)
            self.assertLessEqual(sum(x*x for x in st),1+1e-9)

    def test_invalid_channel_fails(self):
        for kw in ({"dephasing":1.1},{"reset":-1.},{"bias":2.}):
            params=dict(rotation=.1,dephasing=.2,reset=.2,bias=.3)
            params.update(kw)
            with self.assertRaises(ValueError):
                density_step((0.,0.,0.),**params)
        with self.assertRaises(ValueError):
            density_step((2.,0.,0.),rotation=0.,dephasing=0.,reset=0.,bias=0.)

    def test_adversarial_minimax_never_exceeds_empirical_expected(self):
        from trading.edge_lab import TAKER_FEE,BASE_SLIPPAGE,FUNDING_PER_8H
        logs=[.002+.004*math.sin(i) for i in range(32)]
        costs=2*(TAKER_FEE+BASE_SLIPPAGE)+FUNDING_PER_8H*8/32
        empirical=sum(math.log1p(math.expm1(v)-costs) for v in logs)/len(logs)
        self.assertLessEqual(minimax_expected_log(1,logs,atr_fraction=.002),
                             empirical+1e-10)

    def test_worst_case_selects_wait_on_unfavorable_histories(self):
        neg=[-.025+0.001*math.sin(i) for i in range(32)]
        self.assertLess(minimax_expected_log(1,neg,atr_fraction=.003),0)
        self.assertEqual(max(0,minimax_expected_log(1,neg,atr_fraction=.003)),0)

    def test_shock_cost_can_veto_weak_mean_advantage(self):
        weak=[.003 for _ in range(32)]
        self.assertLess(minimax_expected_log(1,weak,atr_fraction=.007),0)

    def test_block_history_never_uses_future_prices(self):
        bars=synthetic(440)
        close=[b["close"] for b in bars]
        before=historical_eight_bar_log_returns(close,360)
        close[390]*=500
        self.assertEqual(before,historical_eight_bar_log_returns(close,360))
        self.assertEqual(len(before),32)

    def test_signals_are_causal_when_unfinished_future_bar_changes(self):
        data=synthetic(440)
        before, _=make_survival_signals(data)
        alternative=[dict(z) for z in data]
        alternative[-1]["close"]=alternative[-1]["high"]
        after,_=make_survival_signals(alternative)
        self.assertEqual(set(before),set(NAMES))
        self.assertEqual(before,after)
        self.assertTrue(all(t<len(data)-1 for rows in before.values()
                            for t,side,atr in rows))

    def test_invalid_samples_rejected(self):
        with self.assertRaises(ValueError):
            minimax_expected_log(0,[.001]*32,atr_fraction=.005)
        with self.assertRaises(ValueError):
            minimax_expected_log(1,[.001]*2,atr_fraction=.005)
        with self.assertRaises(ValueError):
            historical_eight_bar_log_returns([1.]*440,10)


if __name__=="__main__":
    unittest.main()
