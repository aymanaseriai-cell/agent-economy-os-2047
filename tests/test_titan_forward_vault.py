"""Prospective sealed prediction controls: no future signal recomputation."""
import copy
import json
import math
import unittest

from trading.edge_lab import BAR_MS
from trading.titan_forward_vault import (
    STRATEGIES, SEAL_MODE, _hash, _validate_seal, _net_return,
    _lookback_signal, capture, score,
)


def rows(start,n=560):
    out=[]
    prev=100
    for i in range(n):
        op=prev
        close=100+.02*i+math.sin(i/8)*.65
        out.append({"ts":start+i*BAR_MS,"open":op,
                    "high":max(op,close)+.4,
                    "low":min(op,close)-.4,"close":close})
        prev=close
    return out


def timeline():
    initial=rows(1_700_000_100_000//BAR_MS*BAR_MS)
    # Seal after the final completed bar; it is 4-6m into the next candle.
    sealed=initial[-1]["ts"]+BAR_MS+5*60_000
    return initial,sealed


class ForwardVault(unittest.TestCase):
    def test_signal_lookback_never_needs_future(self):
        series,_=timeline()
        first=_lookback_signal(series)
        copied=[dict(x) for x in series]
        # A future placeholder is internal; real final past close is fixed.
        self.assertEqual(first,_lookback_signal(copied))
        self.assertEqual(set(first),set(STRATEGIES))

    def test_seal_precedes_future_market_entry_and_hash(self):
        source,sealed=timeline()
        report=capture(sealed_ms=sealed,
                       get_bars=lambda *_a,**_kw:source,
                       git_sha="testcommit",run_id="4242")
        self.assertTrue(_validate_seal(report))
        self.assertEqual(report["mode"],SEAL_MODE)
        self.assertGreater(report["entry_open_future_ms"],sealed)
        self.assertEqual(len(report["snapshot_rows"]),6)
        self.assertTrue(all(set(x["signals"])==set(STRATEGIES)
                            for x in report["snapshot_rows"]))

    def test_cannot_modify_old_signal_or_cost_or_veto_hash(self):
        source,sealed=timeline()
        report=capture(sealed_ms=sealed,get_bars=lambda *_a,**_kw:source)
        corrupt=copy.deepcopy(report)
        corrupt["snapshot_rows"][0]["signals"][STRATEGIES[0]]=1
        with self.assertRaisesRegex(ValueError,"Seal hash mismatch"):
            _validate_seal(corrupt)
        changed=copy.deepcopy(report)
        changed["costs"]["fee"]=0
        changed["seal_sha256"]=_hash({k:v for k,v in changed.items()
                                     if k!="seal_sha256"})
        with self.assertRaisesRegex(ValueError,"precommitted costs"):
            _validate_seal(changed)

    def test_maturity_requires_all_four_complete_future_candles(self):
        source,sealed=timeline()
        report=capture(sealed_ms=sealed,get_bars=lambda *_a,**_kw:source)
        with self.assertRaisesRegex(ValueError,"not yet matured"):
            score(report,now_ms=report["score_not_before_ms"]-1,
                  get_bars=lambda *_a,**_kw:source)
        with self.assertRaisesRegex(ValueError,"Future completed candles missing"):
            score(report,now_ms=report["score_not_before_ms"]+1,
                  get_bars=lambda *_a,**_kw:source)

    def test_valid_future_market_data_scores_only_sealed_sides(self):
        source,sealed=timeline()
        report=capture(sealed_ms=sealed,get_bars=lambda *_a,**_kw:source)
        entry=report["entry_open_future_ms"]
        old_last=source[-1]
        prev=old_last["close"]
        extended=list(source)
        for ts in range(old_last["ts"]+BAR_MS,
                        report["score_not_before_ms"],BAR_MS):
            close=prev+0.20
            extended.append({"ts":ts,"open":prev,
                             "high":max(prev,close)+.1,
                             "low":min(prev,close)-.1,
                             "close":close})
            prev=close
        self.assertIn(entry,[x["ts"] for x in extended])
        out=score(report,now_ms=report["score_not_before_ms"]+1,
                  get_bars=lambda *_a,**_kw:extended)
        self.assertEqual(out["original_capture_run_id"],report["source_github_run_id"])
        self.assertEqual(out["live_orders"],0)
        self.assertEqual(len(out["records"]),len(STRATEGIES)*6)
        self.assertEqual(sum(v["matured_signal_count"]+
                             sum(x["status"]=="NO_SIGNAL" for x in out["records"]
                                 if x["family"]==name) for name,v in
                             out["strategy_results"].items()),len(STRATEGIES)*6)

    def test_worse_fees_and_slippage_cannot_improve_same_trade(self):
        from trading.edge_lab import TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE
        for side in (-1,1):
            normal=_net_return(side,100,101,fee=TAKER_FEE,slip=BASE_SLIPPAGE)
            stressed=_net_return(side,100,101,fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
            self.assertLess(stressed,normal)

    def test_recent_data_required_before_prospective_seal(self):
        source,sealed=timeline()
        with self.assertRaisesRegex(ValueError,"No recent completed"):
            capture(sealed_ms=sealed+4*BAR_MS,
                    get_bars=lambda *_a,**_kw:source)


if __name__=="__main__":
    unittest.main()
