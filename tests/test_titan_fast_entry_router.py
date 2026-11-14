import unittest
from datetime import datetime, timezone, timedelta
import inspect
from copy import deepcopy
from trading.titan_fast_entry_router import evaluate_fast_entry, VERSION

NOW = 1780000000000
BAR = 15*60*1000
HOUR = 60*60*1000
FOUR_HOURS = 4*HOUR

def make_bars(n, interval, step=.002, price=100.0, *, finish=NOW-BAR):
    start=finish-(n-1)*interval
    out=[]
    for i in range(n):
        close=price*(1+step*i)
        out.append({"ts":start+i*interval,"open":close-.03,
                    "close":close,"high":close+.05,"low":close-.07,
                    "quote_vol":10000.0})
    return out

def fixture(side="LONG"):
    sign=1 if side=="LONG" else -1
    m=make_bars(70,BAR,step=sign*.00018)
    h1=make_bars(40,HOUR,step=sign*.004)
    h4=make_bars(20,FOUR_HOURS,step=sign*.009)
    last=m[-1]
    last["quote_vol"]=30000.0
    last["close"]=(max(b["high"] for b in m[-21:-1])+1.3 if sign>0 else
                   min(b["low"] for b in m[-21:-1])-1.3)
    last["open"]=last["close"]-.03*sign
    last["high"]=max(last["open"],last["close"])+.05
    last["low"]=min(last["open"],last["close"])-.07
    last["ts"]=NOW-BAR
    ticker={"last":last["close"],"spread_bp":4.0,
            "turnover_usdt_est":25_000_000}
    book={"ts":str(NOW-1000),"bids":[["99", "100"]]*20,
          "asks":[["101","100"]]*20}
    trade_side="buy" if sign>0 else "sell"
    trades=[{"side":trade_side,"sz":"10"} for _ in range(40)]
    return m,h1,h4,book,trades,ticker

def run(x, **kwargs):
    return evaluate_fast_entry(*x, derivatives_healthy=True,now_ms=NOW,**kwargs)

class FastEntryResearchTests(unittest.TestCase):
    def test_long_startup_breakout(self):
        r=run(fixture("LONG"))
        self.assertEqual(r["model"],VERSION)
        self.assertEqual(r["direction"],"LONG",r)
        self.assertEqual(r["strategy"],"20_bar_breakout")
        self.assertLess(r["stop"],fixture("LONG")[0][-1]["close"])
        self.assertGreater(r["target"],fixture("LONG")[0][-1]["close"])
        self.assertFalse(r["live_execution_allowed"])
        self.assertEqual(r["order_count"],0)

    def test_short_startup_breakout(self):
        r=run(fixture("SHORT"))
        self.assertEqual(r["direction"],"SHORT",r)
        self.assertEqual(r["strategy"],"20_bar_breakout")
        self.assertGreater(r["stop"],fixture("SHORT")[0][-1]["close"])
        self.assertLess(r["target"],fixture("SHORT")[0][-1]["close"])

    def test_no_derivatives_is_never_an_entry(self):
        x=fixture()
        r=evaluate_fast_entry(*x,derivatives_healthy=False,now_ms=NOW)
        self.assertEqual(r["direction"],"WAIT")
        self.assertEqual(r["reasons"],["derivatives_feed_unverified"])

    def test_stale_book_no_entry(self):
        x=list(fixture())
        x[3]["ts"]=str(NOW-300_000)
        self.assertEqual(run(x)["direction"],"WAIT")

    def test_stale_complete_candle_no_entry(self):
        x=list(fixture())
        x[0][-1]["ts"]=NOW-3*BAR
        self.assertEqual(run(x)["direction"],"WAIT")

    def test_huge_spread_no_entry(self):
        x=list(fixture())
        x[-1]["spread_bp"]=40.0
        self.assertEqual(run(x)["direction"],"WAIT")

    def test_missing_turnover_no_entry(self):
        x=list(fixture())
        x[-1]["turnover_usdt_est"]=0
        self.assertEqual(run(x)["direction"],"WAIT")

    def test_no_trade_flow_no_entry(self):
        x=list(fixture())
        x[4]=[{"side":"sell","sz":"10"} for _ in range(40)]
        self.assertEqual(run(x)["direction"],"WAIT")

    def test_research_abstains_on_zero_volume(self):
        x=list(fixture())
        x[0][-1]["quote_vol"]=0
        self.assertEqual(run(x)["direction"],"WAIT")

    def test_non_finite_public_data_cannot_pass(self):
        x=list(fixture())
        x[0][-1]["close"]=float("nan")
        self.assertEqual(run(x)["direction"],"WAIT")

    def test_no_mutation(self):
        x=fixture()
        frozen=deepcopy(x)
        run(x)
        self.assertEqual(x,frozen)

    def test_no_private_api_or_order_execution(self):
        import trading.titan_fast_entry_router as m
        s=inspect.getsource(m)
        for blocked in ("OKX_API_KEY","OKX_PASSPHRASE","/api/v5/trade/order",
                        "requests.post(","subprocess.run(","client.request(",
                        "allow_post=True","live_execution_allowed\":True"):
            self.assertNotIn(blocked,s)

    def test_any_abstention_has_same_research_only_contract(self):
        x=list(fixture())
        x[4]=[]
        r=run(x)
        self.assertEqual(r["permission"],"RESEARCH_ONLY_NO_ORDERS")
        self.assertFalse(r["live_execution_allowed"])
        self.assertEqual(r["order_count"],0)

if __name__ == "__main__":
    unittest.main()
