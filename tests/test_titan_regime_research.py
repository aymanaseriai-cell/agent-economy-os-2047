"""Tests for locked no-lookahead regime strategies and honest 8.30 goal claims."""
import json
import math
import tempfile
import unittest
from pathlib import Path

from trading.edge_lab import BAR_MS, trade_simulation
from trading.titan_regime_research import (
    CANDIDATES, START_BALANCE_USDT, GOAL_BALANCE_USDT,
    regime_signals, validate_frozen, audit
)


def synthetic_bars(n=480):
    rows=[]
    prior=100.
    for i in range(n):
        close=100+0.025*i+0.8*math.sin(i/8)
        op=prior
        hi=max(op,close)+0.45
        lo=min(op,close)-0.45
        rows.append({"ts":i*BAR_MS,"open":op,"high":hi,"low":lo,"close":close})
        prior=close
    return rows


class LockedRegimeResearch(unittest.TestCase):
    def test_strategies_are_predeclared_not_infinite_parameter_search(self):
        self.assertEqual(CANDIDATES,("regime_breakout","regime_pullback"))
        with self.assertRaises(ValueError):
            regime_signals(synthetic_bars(),"magic_oracle")

    def test_no_lookahead_on_final_completed_bar(self):
        bars=synthetic_bars(480)
        original={name:regime_signals(bars,name) for name in CANDIDATES}
        changed=[dict(bar) for bar in bars]
        changed[-1]["close"]=changed[-1]["high"]
        for name in CANDIDATES:
            self.assertEqual(original[name], regime_signals(changed,name))

    def test_signals_use_completed_bar_and_approved_direction(self):
        bars=synthetic_bars(480)
        for name in CANDIDATES:
            for i,side,atr in regime_signals(bars,name):
                self.assertLess(i,len(bars)-1)
                self.assertGreaterEqual(i,192)
                self.assertIn(side,(-1,1))
                self.assertGreater(atr,0)

    def test_bad_chronology_or_corrupt_ohlc_never_passes(self):
        bars=synthetic_bars()
        bars[200]["ts"]+=1
        with self.assertRaises(ValueError):
            validate_frozen(bars)
        bars=synthetic_bars()
        bars[200]["high"]=bars[200]["low"]-1
        with self.assertRaises(ValueError):
            regime_signals(bars,"regime_breakout")

    def test_all_results_research_only_without_target_probability_claim(self):
        result=audit({"BTC-USDT-SWAP":synthetic_bars()})
        self.assertEqual(result["starting_account_usdt"],START_BALANCE_USDT)
        self.assertEqual(result["target_account_usdt"],GOAL_BALANCE_USDT)
        self.assertIsNone(result["estimated_probability_of_doubling"])
        self.assertIsNone(result["estimated_probability_of_ruin"])
        self.assertFalse(result["actual_account_equity_checked"])
        self.assertFalse(result["live_orders_authorized"])
        self.assertEqual(result["orders_placed"],0)
        self.assertEqual(len(result["summary"]),4)
        for entry in result["summary"].values():
            self.assertEqual(entry["live_readiness"],"NOT_VALIDATED_DO_NOT_TRADE")

    def test_model_fee_stress_is_not_a_free_profit(self):
        bars=synthetic_bars()
        for name in CANDIDATES:
            choices=regime_signals(bars,name)
            base=trade_simulation(bars,choices,start_index=288,end_index=len(bars),
                                  fee=0,slip=0,funding=0)
            stress=trade_simulation(bars,choices,start_index=288,end_index=len(bars),
                                    fee=.0008,slip=.001,funding=.0001)
            self.assertLessEqual(stress["return_pct"],base["return_pct"]+1e-6)

    def test_unknown_symbol_not_rebranded_as_validated(self):
        with self.assertRaises(ValueError):
            audit({"INVALID-USDT-SWAP":synthetic_bars()})


if __name__=="__main__":
    unittest.main()
