import copy
import json
import unittest
from datetime import datetime,timezone
from trading.shadow_observatory import (
    BAR_MS,canonical,diagnostic,freeze,outcome,parse_bars,score,sha,utc_ms,verify_snapshot
)

def make_report(at_ms=1_800_000_000_000,signals=None):
    at_ms=(at_ms//BAR_MS)*BAR_MS + 2*60_000
    ts=datetime.fromtimestamp(at_ms/1000,timezone.utc).isoformat()
    signals=signals or [("BTC-USDT-SWAP","WAIT"),("ETH-USDT-SWAP","LONG")]
    items=[]
    for symbol,side in signals:
        roles=[
            {"agent":f"0{k}_{name}","vote":0,"strength":0,"veto":False,
             "evidence":{"spread_bp":2.5}}
            for k,name in enumerate(("liquidity_sentinel","auction_cartographer",
                "tape_detective","derivatives_intelligence","structure_navigator",
                "risk_marshal"),1)]
        roles[-1]["evidence"]={
            "indicative_stop_not_an_order":98,
            "indicative_target_not_an_order":104
        }
        advanced=[{"system":str(k),"vote":0,"risk":"PASS"} for k in range(7)]
        items.append({
         "symbol":symbol,"signal":side,
         "core_signal_before_advanced":side,
         "quote_price":100,
         "last_complete_15m_candle_ms":(at_ms//BAR_MS-1)*BAR_MS,
         "agents":roles,"advanced_systems":advanced,
         "advanced_veto_reasons":[],"derivatives_data_warnings":[],
         "advanced_confirmations":1,"advanced_contradictions":0,
         "ordinal_buy_points":3,"ordinal_sell_points":0
        })
    return {"mode":"SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY",
            "utc_timestamp":ts,"results":items,"errors":[],
            "markets_selected":len(items)}

def price_bars(from_ms=1_800_000_000_000,n=60):
    start=(from_ms//BAR_MS)*BAR_MS
    return [{"ts":start+i*BAR_MS,"open":100,"high":101,
             "low":99,"close":100} for i in range(n)]

class ShadowObservatoryTests(unittest.TestCase):
    def test_records_wait_and_candidate(self):
        snap=freeze(make_report())
        self.assertEqual(len(snap["decisions"]),2)
        self.assertEqual([x["decision"] for x in snap["decisions"]],["WAIT","LONG"])
        self.assertEqual(snap["orders_placed"],0)
        self.assertEqual(snap["nvidia_gate"],"NOT_EVALUATED_IN_READ_ONLY_SCAN")
        self.assertTrue(verify_snapshot(snap))

    def test_duplicate_scan_has_identical_checksum(self):
        r=make_report()
        self.assertEqual(freeze(r)["snapshot_sha256"],freeze(copy.deepcopy(r))["snapshot_sha256"])

    def test_hash_detects_mutation(self):
        snap=freeze(make_report())
        snap["decisions"][0]["decision"]="LONG"
        with self.assertRaisesRegex(ValueError,"Changed or corrupt"):
            verify_snapshot(snap)

    def test_missing_systems_fails_closed(self):
        report=make_report()
        report["results"][0]["advanced_systems"].pop()
        with self.assertRaisesRegex(ValueError,"Missing council"):
            freeze(report)

    def test_wait_not_counted_as_trade(self):
        report=make_report(signals=[("BTC-USDT-SWAP","WAIT")])
        snap=freeze(report)
        bars=price_bars()
        z=score([snap],{"BTC-USDT-SWAP":bars})
        self.assertEqual(z["summary"]["wait_count"],1)
        self.assertEqual(z["summary"]["candidate_count"],0)
        self.assertEqual(z["rows"][0]["60m"]["status"],"abstained")

    def test_pending_horizon_not_scored(self):
        snap=freeze(make_report(signals=[("ETH-USDT-SWAP","LONG")]))
        bars=price_bars(n=4)
        x=score([snap],{"ETH-USDT-SWAP":bars})
        self.assertEqual(x["summary"]["primary_matured_1h_count"],0)
        self.assertEqual(x["rows"][0]["60m"]["status"],"immature_or_missing")

    def test_no_entry_on_prepublication_candle(self):
        snap=freeze(make_report(signals=[("ETH-USDT-SWAP","LONG")]))
        bars=price_bars()
        sig=snap["decisions"][0]
        obs=outcome(sig,snap["timestamp_utc"],bars,4,fee=0,slippage=0,funding=0)
        self.assertEqual(obs["status"],"matured")
        bars[0]["low"]=.1
        bars[0]["high"]=1000
        self.assertEqual(obs,outcome(sig,snap["timestamp_utc"],bars,4,fee=0,slippage=0,funding=0))

    def test_stop_wins_intrabar_ambiguity(self):
        snap=freeze(make_report(signals=[("ETH-USDT-SWAP","LONG")]))
        bars=price_bars()
        bars[1]={"ts":bars[1]["ts"],"open":100,"high":105,"low":97,"close":100}
        o=outcome(snap["decisions"][0],snap["timestamp_utc"],bars,4)
        self.assertEqual(o["outcome"],"stop")
        self.assertLess(o["net_unlevered_pct"],0)

    def test_cost_stress_reduces_gain(self):
        snap=freeze(make_report(signals=[("ETH-USDT-SWAP","LONG")]))
        bars=price_bars()
        s=snap["decisions"][0]
        z=outcome(s,snap["timestamp_utc"],bars,4,fee=0,slippage=0,funding=0)
        x=outcome(s,snap["timestamp_utc"],bars,4)
        self.assertLess(x["net_unlevered_pct"],z["net_unlevered_pct"])

    def test_correlated_episode_deduplicated(self):
        a=freeze(make_report(signals=[("BTC-USDT-SWAP","LONG")]))
        b=freeze(make_report(at_ms=1_800_000_000_000+BAR_MS,
                            signals=[("BTC-USDT-SWAP","LONG")]))
        z=score([b,a],{"BTC-USDT-SWAP":price_bars()})
        self.assertEqual(z["summary"]["candidate_count"],2)
        self.assertEqual(z["summary"]["correlated_repeat_count"],1)
        self.assertEqual(sum(x["episode_primary"] for x in z["rows"]),1)

    def test_same_scan_repeated_is_deduplicated(self):
        s=freeze(make_report(signals=[("BTC-USDT-SWAP","LONG")]))
        z=score([s,s],{"BTC-USDT-SWAP":price_bars()})
        self.assertEqual(z["summary"]["snapshots"],1)

    def test_not_claim_profit_edge_on_too_few_samples(self):
        s=freeze(make_report(signals=[("BTC-USDT-SWAP","LONG")]))
        z=score([s],{"BTC-USDT-SWAP":price_bars()})
        self.assertFalse(z["summary"]["edge_established"])
        self.assertEqual(z["summary"]["status"],"INSUFFICIENT_PROSPECTIVE_EVIDENCE")

    def test_policy_version_firewall_never_blends_old_and_new(self):
        a=freeze(make_report(signals=[("BTC-USDT-SWAP","LONG")]))
        b=freeze(make_report(at_ms=1_800_000_000_000+20*BAR_MS,
                             signals=[("BTC-USDT-SWAP","LONG")]))
        b["decision_policy_sha256"]="post_revision_of_decision_rules"
        b["snapshot_sha256"]=sha({k:v for k,v in b.items() if k!="snapshot_sha256"})
        bars=price_bars(n=65)
        z=score([a,b],{"BTC-USDT-SWAP":bars})
        self.assertEqual(z["summary"]["unique_decision_policy_versions"],2)
        self.assertEqual(z["summary"]["primary_matured_1h_count"],1)
        self.assertEqual(z["summary"]["current_decision_policy_sha256"],
                         "post_revision_of_decision_rules")

    def test_empty_candles_excluded(self):
        rows=[
           ["0","99","101","98","100","0","0","1","1"],
           ["900000","1","2","0.5","1.5","0","0","1","0"]]
        bars=parse_bars(rows)
        self.assertEqual(len(bars),1)

    def test_attribution_identifies_root_blocker(self):
        x=freeze(make_report())["decisions"][0]
        x["core_before_filters"]="WAIT"
        x["advanced_veto_reasons"]=["05_depth_fragility:veto"]
        self.assertEqual(diagnostic(x),["core_no_consensus","seven_quant_veto"])

if __name__=="__main__":
    unittest.main()
