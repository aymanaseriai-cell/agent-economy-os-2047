"""Quantum recurrence audit invariants, deterministic fixtures, zero order calls."""
import math
import unittest
from trading.edge_lab import BAR_MS
from trading.titan_quantum_recurrence import (
    FAMILIES,SYMBOLS,capital_feasibility,quantum_family_signals,
    trade_day_stats,_score_segments,assess
)


def fake_bars(n=520):
    result=[];prev=100.0
    for i in range(n):
        p=100+i*.007+.25*math.sin(i/13)
        result.append({"ts":i*BAR_MS,"open":prev,
                       "high":max(p,prev)+.3,
                       "low":min(p,prev)-.3,
                       "close":p})
        prev=p
    return result


class RecurrenceTests(unittest.TestCase):
    def test_new_basket_not_recycled_prior_18(self):
        self.assertEqual(len(set(SYMBOLS)),6)
        self.assertFalse(set(SYMBOLS) & {
            "BTC-USDT-SWAP","ETH-USDT-SWAP","SOL-USDT-SWAP",
            "XRP-USDT-SWAP","DOGE-USDT-SWAP","SUI-USDT-SWAP",
            "LTC-USDT-SWAP","ADA-USDT-SWAP","AVAX-USDT-SWAP",
            "LINK-USDT-SWAP","DOT-USDT-SWAP","APT-USDT-SWAP",
            "BCH-USDT-SWAP","ETC-USDT-SWAP","XLM-USDT-SWAP",
            "NEAR-USDT-SWAP","ATOM-USDT-SWAP","UNI-USDT-SWAP"})

    def test_signals_causal_unfinished_last_candle_never_read(self):
        bars=fake_bars()
        base=quantum_family_signals(bars)
        corrupted=[dict(b) for b in bars]
        corrupted[-1]["close"]=corrupted[-1]["high"]
        observed=quantum_family_signals(corrupted)
        self.assertEqual(base,observed)
        self.assertEqual(set(base),set(FAMILIES))
        self.assertTrue(all(t<len(bars)-1 for v in base.values()
                            for t,side,atr in v))

    def test_public_small_account_minimum_contract_cannot_be_ignored(self):
        bars=fake_bars()
        spec=dict(instId="TRX-USDT-SWAP",ctType="linear",state="live",
                  ctValCcy="TRX",ctVal="100",minSz="20",lotSz="1")
        x=capital_feasibility("TRX-USDT-SWAP",bars,spec)
        self.assertFalse(x["can_place_guarded_min_lot"])
        self.assertEqual(x["reason"],"MIN_LOT_EXCEEDS_SMALL_CAPITAL_BUDGET")

    def test_public_small_contract_can_pass_illustrative_only(self):
        bars=fake_bars()
        spec=dict(instId="TRX-USDT-SWAP",state="live",
                  ctValCcy="TRX",ctVal="0.001",minSz="1",lotSz="1")
        x=capital_feasibility("TRX-USDT-SWAP",bars,spec)
        self.assertTrue(x["can_place_guarded_min_lot"])
        self.assertFalse(x["user_actual_account_checked"])

    def test_missing_or_unknown_public_specs_rejects(self):
        bars=fake_bars()
        self.assertFalse(capital_feasibility("TRX-USDT-SWAP",bars,None)["can_place_guarded_min_lot"])
        self.assertFalse(capital_feasibility("TRX-USDT-SWAP",bars,
                 {"instId":"TRX-USDT-SWAP","state":"live"})["can_place_guarded_min_lot"])

    def test_profit_day_counts_not_individual_correlated_wins(self):
        records=[{"exit_ts":i*BAR_MS,"net_usd":1 if i<2 else -3} for i in range(3)]
        r=trade_day_stats(records)
        self.assertEqual(r["unique_exit_days"],1)
        self.assertEqual(r["positive_exit_days"],0)
        self.assertEqual(r["negative_exit_days"],1)

    def test_half_splits_nonoverlap(self):
        bars=fake_bars(520)
        ss=_score_segments(bars,[],390)
        self.assertEqual(len(ss),3)
        self.assertTrue(all(z["trades"]==0 and z["net_pct"]==0 for z in ss))

    def test_no_partial_market_success_claim(self):
        bars=fake_bars()
        with self.assertRaises(ValueError):
            assess({SYMBOLS[0]:bars},{})

    def test_refuse_fake_small_90d_set(self):
        bars=fake_bars()
        with self.assertRaises(ValueError):
            assess({s:bars for s in SYMBOLS},{})


if __name__=="__main__":
    unittest.main()
