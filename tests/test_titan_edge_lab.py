import math
import unittest
from trading.titan_edge_lab import SYSTEMS, evaluate_edge_lab,signal_at_close
from trading.titan_walkforward import walk_forward_audit, _simulate

def candles(n=480, step=0.00035, oscillation=0.001):
    out=[]
    for i in range(n):
        p=100*math.exp(step*i+oscillation*math.sin(i/5))
        op=p*(1-0.0005)
        out.append({"ts":i*900000,"open":op,"high":p*1.003,
                    "low":op*0.997,"close":p,"quote_vol":20000+5000*(i%9)})
    return out

class EdgeLabTests(unittest.TestCase):
    def test_eight_readonly_finite_market_metrics(self):
        book={"bids":[["100","20"] for _ in range(20)],"asks":[["100","18"] for _ in range(20)]}
        args=(candles(200),candles(80),candles(50),book)
        a=evaluate_edge_lab(*args)
        self.assertEqual(a,evaluate_edge_lab(*args))
        self.assertEqual(a["edge_system_count"],len(SYSTEMS))
        self.assertEqual(len(a["systems"]),8)
        self.assertTrue(a["data_valid"])
        self.assertTrue(a["shadow_only"])
        self.assertEqual(a["orders_placed"],0)
        for item in a["systems"]:
            for metric in item["metrics"].values():
                if metric is not None:
                    self.assertTrue(math.isfinite(metric))

    def test_corrupt_ohlc_or_time_is_rejected(self):
        b=candles(200)
        b[8]["ts"]=b[7]["ts"]
        self.assertFalse(evaluate_edge_lab(b,candles(80),candles(50),{})["data_valid"])
        b=candles(200)
        b[-1]["high"]=0
        self.assertFalse(evaluate_edge_lab(b,candles(80),candles(50),{})["data_valid"])

    def test_donchian_excludes_the_current_breakout_bar(self):
        b=candles(100,step=0.0,oscillation=0.0)
        b[-1]["close"]=103.0
        b[-1]["high"]=103.1
        self.assertEqual(signal_at_close(b,len(b)-1,"donchian_breakout"),1)

    def test_future_candles_cannot_change_earlier_signal(self):
        b=candles(500)
        for strat in ("ema_trend","donchian_breakout","bollinger_reversion"):
            orig=signal_at_close(b,200,strat)
            altered=[dict(x) for x in b]
            for i in range(201,len(altered)):
                altered[i]["close"]*=5
                altered[i]["high"]*=5
            self.assertEqual(orig,signal_at_close(altered,200,strat))

    def test_walkforward_chronological_holdout_and_cost_drag(self):
        b=candles(500)
        zero=walk_forward_audit(b,fee_bp_per_side=0,slippage_bp_per_side=0)
        fees=walk_forward_audit(b,fee_bp_per_side=10,slippage_bp_per_side=10)
        self.assertIsNotNone(zero["selected"])
        self.assertIn(zero["status"],("SHADOW_TESTED_NOT_VALIDATED","INSUFFICIENT_TEST_TRADES"))
        self.assertFalse(zero["can_trade_live"])
        self.assertFalse(fees["can_trade_live"])
        # Compare EXACTLY the same holdout signals so strategy re-selection
        # cannot hide the effect of higher round-trip costs.
        split=zero["train_bars"]
        unchanged=_simulate(b,zero["selected"],split-1,len(b)-1,0.0)
        costly=_simulate(b,zero["selected"],split-1,len(b)-1,0.004)
        self.assertLessEqual(costly["total_return_pct"],unchanged["total_return_pct"]+0.0001)
        self.assertEqual(fees["train_bars"]+fees["test_bars"],len(b))

    def test_selection_cannot_see_test_period(self):
        b=candles(500)
        original=walk_forward_audit(b)
        split=original["train_bars"]
        changed=[dict(x) for x in b]
        # Change ONLY chronological holdout rows, never training rows.
        for i in range(split,len(changed)):
            p=changed[i]["close"]*(0.95 if i%2 else 1.05)
            changed[i]["open"]=p
            changed[i]["close"]=p*1.01
            changed[i]["high"]=p*1.02
            changed[i]["low"]=p*0.99
        alternate=walk_forward_audit(changed)
        self.assertEqual(original["selected"],alternate["selected"])
        self.assertEqual(original["train"],alternate["train"])

    def test_short_four_hour_frame_does_not_invalidate_all_metrics(self):
        r=evaluate_edge_lab(candles(200),candles(80),candles(15),{})
        self.assertTrue(r["data_valid"])

    def test_walkforward_too_few_candles_or_invalid_costs(self):
        self.assertEqual(walk_forward_audit(candles(200))["status"],"INVALID_OR_INSUFFICIENT_INPUT")
        self.assertEqual(walk_forward_audit(candles(500),fee_bp_per_side=-1)["status"],"INVALID_OR_INSUFFICIENT_INPUT")

if __name__=="__main__":
    unittest.main()
