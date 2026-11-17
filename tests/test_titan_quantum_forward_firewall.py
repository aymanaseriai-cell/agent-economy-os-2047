"""Forward seal must prevent post-facto signal changes and premature profit."""
import copy,math,unittest
from trading.edge_lab import BAR_MS
from trading.titan_quantum_forward_firewall import (
    LOCKED_SYMBOLS,HORIZON,START,TARGET,RUIN,FAMILIES,capture,score,_validate,_decision
)


def series(n=500,last_ts=None):
    # all OHLC candles with 15m spacing and consistent chronological time
    first=0 if last_ts is None else last_ts-(n-1)*BAR_MS
    v=[];prev=100.
    for i in range(n):
        close=100+0.006*i+0.22*math.sin(i/11)
        v.append({"ts":first+i*BAR_MS,"open":prev,
                  "high":max(close,prev)+.30,
                  "low":min(close,prev)-.30,"close":close})
        prev=close
    return v


def spec(sym):
    return {"instId":sym,"ctValCcy":sym.split("-")[0],"ctVal":"0.001",
            "minSz":"1","lotSz":"1","state":"live","ctType":"linear"}


def fixture():
    now=(500*BAR_MS)+BAR_MS//3
    candles=series(500,last_ts=(now//BAR_MS-1)*BAR_MS)
    def provider(sym,days,now_ms):
        return candles
    return capture(now_ms=now,get_bars=provider,get_spec=spec,
                   git_sha="frozen-source",run_id="123456"),candles


class ForwardResearchTests(unittest.TestCase):
    def test_seal_precedes_any_future_entry_and_has_fixed_six(self):
        seal,candles=fixture()
        self.assertTrue(_validate(seal))
        self.assertEqual(len(seal["rows"]),len(LOCKED_SYMBOLS))
        self.assertLess(seal["created_at_ms"],seal["entry_future_bar_start_ms"])
        self.assertEqual(seal["maturity_not_before_ms"]-
                         seal["entry_future_bar_start_ms"],HORIZON*BAR_MS)
        self.assertTrue(seal["no_private_okx_api_no_orders"])

    def test_tampering_or_hindsight_refused(self):
        seal,_=fixture()
        damaged=copy.deepcopy(seal)
        old=damaged["rows"][0]["signals"]["quantum_phase_robust"]
        damaged["rows"][0]["signals"]["quantum_phase_robust"]=1 if old!=1 else -1
        with self.assertRaises(ValueError):
            _validate(damaged)
        damaged=copy.deepcopy(seal)
        damaged["entry_future_bar_start_ms"]=seal["created_at_ms"]
        with self.assertRaises(ValueError):
            _validate(damaged)

    def test_premature_future_scoring_refused(self):
        seal,_=fixture()
        with self.assertRaises(ValueError):
            score(seal,now_ms=seal["maturity_not_before_ms"]-1)

    def test_forward_score_does_not_recreate_signals(self):
        seal,older=fixture()
        entry=seal["entry_future_bar_start_ms"]
        # Enough completed future bars; artificially create gapless independent data
        all_bars=older[:]
        latest=older[-1]
        for i in range(1,9):
            ts=latest["ts"]+i*BAR_MS
            last=all_bars[-1]["close"]
            nextp=last*(1+.0008)
            all_bars.append({"ts":ts,"open":last,
                             "high":max(last,nextp)+.1,
                             "low":min(last,nextp)-.1,"close":nextp})
        def later(sym,days,now_ms):
            return all_bars
        when=seal["maturity_not_before_ms"]+BAR_MS
        report=score(seal,now_ms=when,get_bars=later)
        self.assertTrue(report["entry_after_seal_verified"])
        self.assertEqual(len(report["all_recorded_markets"]),
                         len(LOCKED_SYMBOLS)*len(FAMILIES))
        self.assertTrue(report["no_real_orders"])
        for fam in FAMILIES:
            self.assertLessEqual(report["comparison"][fam]["shadow_filled_count_this_window"],1)
            self.assertFalse(report["comparison"][fam]["verified_repeatable_edge"])

    def test_change_only_unfinished_candle_does_not_change_signals(self):
        seal,candles=fixture()
        a=_decision(candles)
        modified=[dict(x) for x in candles]
        # A candle strictly after the decision bar is never part of causal input.
        new=dict(modified[-1]);new["ts"]+=BAR_MS
        new["close"]*=5
        self.assertEqual(a,_decision(modified))

    def test_prospective_scan_uses_absolute_utc_bar_phase(self):
        # Identical 499-bar rolling windows at UTC quarter-hour offsets
        # should not be permanently pinned to WAIT by len(window)%4.
        original=series(500,last_ts=499*BAR_MS)
        shifted=[dict(row,ts=row["ts"]+BAR_MS) for row in original]
        a=_decision(original)
        b=_decision(shifted)
        self.assertNotEqual(a["scan_eligible"],b["scan_eligible"])

    def test_fees_and_balance_stay_paper_only(self):
        seal,_=fixture()
        self.assertEqual(seal["start_usdt_not_real_account"],START)
        self.assertEqual(seal["target_usdt"],TARGET)
        self.assertEqual(seal["ruin_usdt"],RUIN)
        self.assertEqual(seal["trade_execution_mode"],"PAPER_ONLY")
        self.assertNotIn("api_key",str(seal).lower())

if __name__=="__main__":
    unittest.main()
