"""Reproducible guards for frozen 128% breakout paper challenger."""
import unittest
from unittest.mock import patch
from trading import titan128_breakout_blind as b
from trading.edge_lab import BAR_MS

def candles(n=480):
    result=[]
    for i in range(n):
        price=100 + i*.018
        result.append({"ts":i*BAR_MS,"open":price,"close":price,
                       "high":price+.13,"low":price-.13})
    return result

class BreakoutResearchTest(unittest.TestCase):
    def test_target_is_exact_and_no_credentials_needed(self):
        self.assertEqual((b.START,b.GOAL,b.RUIN),(4.15,9.462,.83))
        self.assertEqual(b.LEVERAGES,(3.,10.))
        self.assertTrue(b.FORBIDDEN.isdisjoint(b.UNIVERSE))

    def test_later_candle_cannot_rewrite_earlier_signal(self):
        bars=candles()
        a=b.breakout_signals(bars)
        mutate=[dict(x) for x in bars]
        mutate[-1]["close"]=mutate[-1]["high"]
        mutate[-1]["high"]*=4
        self.assertEqual(a,b.breakout_signals(mutate))

    def test_past_lookback_excludes_current_bar(self):
        bars=candles()
        bars[400]["close"]=110.
        bars[400]["high"]=110.1
        # Prefix before bar 400 cannot be rewritten by its much higher price.
        prefix=b.breakout_signals(bars[:400])
        full=b.breakout_signals(bars)
        self.assertEqual(prefix,[x for x in full if x[0]<399])

    def test_no_signals_means_no_profit_claim(self):
        sym="ADA-USDT-SWAP"
        with patch.object(b.qsi,"sim_one") as sim:
            r=b.paper({sym:candles()},{sym:{}},{sym:[]},leverage=3.,
                      start=224,end=480,fee=.0005,slip=.0003)
        sim.assert_not_called()
        self.assertEqual(r["end_usdt"],4.15)
        self.assertFalse(r["reached128_on_closed_paper_trade"])

    def test_unrealized_high_is_not_a_closed_profit(self):
        sym="ADA-USDT-SWAP"
        trade={"equity_after":4.18,"exit_i":260,
               "status":"tp","entry_fee_usdt":0.,
               "exit_fee_usdt":0.,"unrealized_peak_usdt":999.}
        with patch.object(b.qsi,"sim_one",return_value=trade):
            r=b.paper({sym:candles()},{sym:{}},{sym:[(250,1,1.,.5)]},
                      leverage=3.,start=224,end=480,
                      fee=.0005,slip=.0003)
        self.assertFalse(r["reached128_on_closed_paper_trade"])
        self.assertIsNone(r["first_goal_closed_exit_i"])

    def test_not_six_markets_fails_closed(self):
        with self.assertRaises(ValueError):
            b.evaluate({"ADA-USDT-SWAP":candles()},
                       {"ADA-USDT-SWAP":{}}, {}, 0)

if __name__=="__main__":
    unittest.main()
