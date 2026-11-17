"""Causal future-price firewall, same-info controls, and real-lot paper stop."""
import unittest,math
from trading import titan_quantum_frictions_veto as q
from trading.edge_lab import BAR_MS


def candles(n=430):
    out=[];p=100.
    for i in range(n):
        c=100+i*.010+.28*math.sin(i/17)
        out.append({"ts":i*BAR_MS,"open":p,
            "high":max(p,c)+.31,"low":min(p,c)-.31,"close":c})
        p=c
    return out


class QFRVTest(unittest.TestCase):
    def test_128_goal_exact(self):
        self.assertEqual(q.START,4.15)
        self.assertEqual(q.TARGET128,9.462)
        self.assertEqual(q.RUIN,.83)

    def test_unobserved_last_candle_cannot_affect_prior_signals(self):
        bars=candles()
        a=q.signal_universe(bars)
        change=[dict(x) for x in bars]
        change[-1]["high"]*=3
        change[-1]["close"]=change[-1]["high"]
        self.assertEqual(a,q.signal_universe(change))

    def test_original_qsi_policy_identical_unmodified(self):
        from trading import titan_quantum_survival_interferometer as qsi
        bars=candles()
        a=q.signal_universe(bars)
        baseline=qsi.candidate_stream(bars)
        self.assertEqual(a["quantum_robust_ungated"],
                         baseline["quantum_phase_robust"])
        self.assertEqual(a["classical_ungated"],
                         baseline["classical_same_features"])

    def test_gate_has_no_future_prices(self):
        b=candles()
        cl=[x["close"] for x in b]
        from trading.edge_lab import ema_series
        fa,sl=ema_series(cl,24),ema_series(cl,96)
        x=q._is_causal_trend(b,cl,fa,sl,400,1,.5)
        mutated=[dict(z) for z in b]
        mutated[401]["close"]=mutated[401]["high"]
        c2=[z["close"] for z in mutated]
        fa2,sl2=ema_series(c2,24),ema_series(c2,96)
        self.assertEqual(x,q._is_causal_trend(mutated,c2,fa2,sl2,400,1,.5))

    def test_stress_cost_gate_rejects_small_moves(self):
        self.assertFalse(q._stress_fee_veto(100,.001))
        self.assertTrue(q._stress_fee_veto(100,10))

    def test_classical_frequency_only_train_event_counts(self):
        original={"AR-USDT-SWAP":{
            name:[] for name in q.POLICIES}}
        quantum=[(i,1,1.,.3) for i in range(230,260)]
        classical=[(i,1,1.,.3) for i in range(230,290)]
        original["AR-USDT-SWAP"]["quantum_cost_trend"]=quantum
        original["AR-USDT-SWAP"]["classical_cost_trend"]=classical
        ratio1=q._match_frequency(original,265)
        candidate=list(original["AR-USDT-SWAP"]["classical_train_frequency_matched"])
        original["AR-USDT-SWAP"]["classical_cost_trend"]+=[(800,1,1.,.3)]
        ratio2=q._match_frequency(original,265)
        self.assertEqual(ratio1,ratio2)
        self.assertEqual(candidate,original["AR-USDT-SWAP"][
            "classical_train_frequency_matched"][:-1]
            if original["AR-USDT-SWAP"]["classical_train_frequency_matched"][-1][0]==800
            else original["AR-USDT-SWAP"]["classical_train_frequency_matched"])

    def test_no_signals_is_zero_return(self):
        b=candles()
        sym="AR-USDT-SWAP"
        policies={z:[] for z in q.POLICIES}
        result=q.paper({sym:b},{sym:{}},{sym:policies},
                       policy="quantum_cost_trend",leverage=3.,
                       start=224,end=len(b),
                       fee=.0005,slip=.0003)
        self.assertEqual(result["end_usdt"],4.15)
        self.assertEqual(result["trades"],0)
        self.assertFalse(result["hit_128_after_closed_trade"])

    def test_unrealized_peak_is_not_a_closed_128_percent_win(self):
        """Intratrade price peaks must not be reported as realized +128%."""
        from unittest.mock import patch
        sym="AR-USDT-SWAP"
        bars=candles()
        votes={name:[] for name in q.POLICIES}
        votes["quantum_cost_trend"]=[(250,1,1.,.5)]
        closed_trade={
            "equity_after":4.20,"exit_i":255,"day":"2026-11-17",
            "net_usdt":.05,"status":"tp","entry_fee_usdt":0.,
            "exit_fee_usdt":0.,"unrealized_peak_usdt":1000.,
        }
        with patch.object(q.qsi,"sim_one",return_value=closed_trade) as sim:
            r=q.paper({sym:bars},{sym:{}},{sym:votes},
                      policy="quantum_cost_trend",leverage=3.,
                      start=224,end=len(bars),fee=.0005,slip=.0003)
        sim.assert_called_once()
        self.assertEqual(r["trades"],1)
        self.assertEqual(r["end_usdt"],4.20)
        self.assertFalse(r["hit_128_after_closed_trade"])
        self.assertIsNone(r["first_target_exit_i"])

    def test_reject_old_research_crypto_panel(self):
        self.assertTrue({"CHZ","FLOW","1INCH","CFX"} <= q.PREVIOUS_QSI_QTRW_QGFW)
        self.assertTrue(q.PREVIOUS_QSI_QTRW_QGFW.isdisjoint(q.UNIVERSE))

    def test_incomplete_six_market_report_fails_closed(self):
        with self.assertRaises(ValueError):
            q.experiment({"AR-USDT-SWAP":candles()},{})


if __name__=="__main__":
    unittest.main()
