import unittest
from datetime import datetime, timezone, timedelta
from copy import deepcopy
from trading.shadow_observatory import freeze, sha, BAR_MS
from trading.titan_fast_entry_forward import evaluate, bootstrap_lower5

BASE=datetime(2026,1,1,tzinfo=timezone.utc)

def snap(i, *, policy="a", direction="LONG", strategy="20_bar_breakout",
         live=False, size=1, source=100.0):
    ts=BASE+timedelta(hours=4*i,minutes=1)
    symbol=f"SYM{i}-USDT-SWAP"
    p={"direction":direction,"strategy":strategy,"stop":98.0 if direction=="LONG" else 102.0,
       "target":104.0 if direction=="LONG" else 96.0,
       "research_only_no_orders":not live}
    raw={"schema":"quant2037-shadow-v1","mode":"PUBLIC_ONLY_NO_TRADES",
         "timestamp_utc":ts.isoformat().replace("+00:00","Z"),
         "decision_policy_sha256":policy,
         "decisions":[{"symbol":symbol,"source_price":source,
                       "fast_entry_research":p}],"errors":[],"orders_placed":0}
    raw["snapshot_sha256"]=sha(raw)
    ms=int(ts.timestamp()*1000)
    start=((ms+BAR_MS-1)//BAR_MS)*BAR_MS
    prices=[{"ts":start+j*BAR_MS,"open":100.0,
             "high":101.0 if direction=="LONG" else 101.0,
             "low":99.0,
             "close":100.8 if direction=="LONG" else 99.2} for j in range(4)]
    return raw,symbol,prices

def many(n,**kwargs):
    rows=[];hist={}
    for i in range(n):
        s,sym,bars=snap(i,**kwargs)
        rows.append(s);hist[sym]=bars
    return rows,hist

class FastEntryForwardTests(unittest.TestCase):
    def test_no_archive_does_not_authorize_trades(self):
        x=evaluate([],{})
        self.assertEqual(x["candidate_episodes_matured"],0)
        self.assertFalse(x["live_trading_approved"])
        self.assertEqual(x["governance"],"INSUFFICIENT_FORWARD_EVIDENCE")

    def test_one_candidate_uses_next_candle_and_stressed_cost(self):
        s,sym,bars=snap(0)
        x=evaluate([s],{sym:bars})
        self.assertEqual(x["candidate_episodes_matured"],1)
        self.assertEqual(x["live_order_count"],0)
        self.assertEqual(x["chronological_holdout_count"],0)

    def test_incomplete_future_bars_excluded(self):
        s,sym,bars=snap(0)
        x=evaluate([s],{sym:bars[:2]})
        self.assertEqual(x["candidate_episodes_matured"],0)

    def test_missing_market_history_fails_closed(self):
        s,sym,bars=snap(0)
        with self.assertRaisesRegex(ValueError,"Actual future candles"):
            evaluate([s],{})

    def test_tampered_hash_fails_closed(self):
        s,sym,bars=snap(0)
        s["decisions"][0]["fast_entry_research"]["direction"]="SHORT"
        with self.assertRaises(ValueError):
            evaluate([s],{sym:bars})

    def test_candidate_without_research_guard_fails_closed(self):
        s,sym,bars=snap(0,live=True)
        with self.assertRaises(ValueError):
            evaluate([s],{sym:bars})

    def test_same_snapshot_repeated_not_inflate_sample(self):
        s,sym,bars=snap(0)
        x=evaluate([s,s],{sym:bars})
        self.assertEqual(x["archived_snapshot_count"],1)
        self.assertEqual(x["candidate_episodes_matured"],1)

    def test_old_fingerprint_ignored(self):
        a,aa,ab=snap(0,policy="old")
        b,bb,bc=snap(1,policy="new")
        x=evaluate([a,b],{aa:ab,bb:bc})
        self.assertEqual(x["candidate_episodes_matured"],1)

    def test_sufficient_episodes_never_auto_approve(self):
        rows,hist=many(150)
        x=evaluate(rows,hist)
        self.assertEqual(x["candidate_episodes_matured"],150)
        self.assertEqual(x["independent_utc_days"],25)
        self.assertEqual(x["governance"],"RESEARCH_REVIEW_ELIGIBLE_NOT_LIVE_APPROVED")
        self.assertFalse(x["live_trading_approved"])
        self.assertGreater(x["holdout_stressed_bootstrap_lower5_mean_pct"],0)

    def test_legacy_without_fast_data_remains_safe(self):
        s,sym,bars=snap(0)
        del s["decisions"][0]["fast_entry_research"]
        s["snapshot_sha256"]=sha({k:v for k,v in s.items() if k!="snapshot_sha256"})
        x=evaluate([s],{sym:bars})
        self.assertEqual(x["candidate_episodes_matured"],0)

    def test_freeze_snapshot_preserves_fast_decision_and_digest(self):
        roles=[{"agent":name,"evidence":{"spread_bp":4.0},"vote":0,
                "strength":0,"veto":False} for name in (
                  "01_liquidity_sentinel","02_auction_cartographer",
                  "03_tape_detective","04_derivatives_intelligence",
                  "05_structure_navigator","06_risk_marshal")]
        advanced=[{"system":str(i),"vote":0,"risk":"PASS"} for i in range(7)]
        fast={"model":"fast-entry-research-v1","permission":"RESEARCH_ONLY_NO_ORDERS",
              "live_execution_allowed":False,"order_count":0,
              "direction":"LONG","strategy":"20_bar_breakout",
              "stop":98.0,"target":104.0}
        data={"mode":"SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY",
              "utc_timestamp":BASE.isoformat(),
              "results":[{"symbol":"ABC-USDT-SWAP","signal":"WAIT",
                          "quote_price":100,"agents":roles,
                          "advanced_systems":advanced,"fast_entry_research":fast}]}
        frozen=freeze(data)
        self.assertEqual(frozen["decisions"][0]["fast_entry_research"]["direction"],"LONG")
        from trading.shadow_observatory import verify_snapshot
        self.assertTrue(verify_snapshot(frozen))

    def test_fingerprint_includes_fast_router_source(self):
        from pathlib import Path
        from trading.shadow_observatory import policy_fingerprint
        self.assertEqual(len(policy_fingerprint()),64)
        self.assertNotEqual(policy_fingerprint(),"unavailable_local_fixture")

    def test_empty_holdout_cannot_claim_positive_significance(self):
        self.assertIsNone(bootstrap_lower5([1.0]*29))

if __name__=="__main__":
    unittest.main()
