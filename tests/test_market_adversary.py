import copy
import json
import unittest
from unittest.mock import patch

from trading import market_adversary as a
from trading import six_agent_council as c
from trading.quant2037 import evaluate_advanced

MS=1_800_000_000_000
Q=900000
def history(n,interval,base=100):
    start=MS-(n+1)*interval
    rows=[]
    for i in range(n):
        cl=base+i*.005
        rows.append([str(start+i*interval),str(cl-.01),str(cl+.13),
                     str(cl-.13),str(cl),"1000","0","1000000","1"])
    return rows[::-1]

def fixture():
    book={
       "ts":str(MS-1000),
       "bids":[[str(100-i*.01),str(20+i),"0","1"] for i in range(25)],
       "asks":[[str(100.1+i*.01),str(25+i),"0","1"] for i in range(25)]}
    trades=[{"ts":str(MS-i*1000),"side":"buy" if i%3 else "sell",
             "sz":str(i%10+1)} for i in range(80)]
    return {
      "ticker":{"symbol":"BTC-USDT-SWAP","last":100.05,
                "bid":100.04,"ask":100.06,"spread_bp":2,
                "turnover_usdt_est":30_000_000},
      "bars15":history(205,Q),
      "bars1h":history(60,4*Q),
      "bars4h":history(30,16*Q),
      "book":book,"trades":trades,
      "funding":{"fundingRate":"0.0002"},
      "interest":{"oiUsd":"15000000","oiCcy":"100000"},
      "mark":{"markPx":"100.04"},
      "missing_derivative_feeds":[],
      "captured_at_ms":MS,
      "source":"OKX_PUBLIC_MARKET_ENDPOINTS_ONLY"
    }

class OriginalModelAdversaryTests(unittest.TestCase):
    def test_replay_6_and_7_exactly(self):
        frozen=fixture()
        original=a.replay_original(frozen)
        self.assertEqual(len(original["agents"]),6)
        self.assertEqual(len(original["advanced_systems"]),7)
        self.assertEqual(original["execution"],"DISABLED")
        self.assertEqual(original["order_count"],0)
        self.assertIn(original["signal"],["LONG","SHORT","WAIT"])

    def test_reproducible_frozen_decisions(self):
        frozen=fixture()
        self.assertEqual(a.replay_original(frozen),a.replay_original(copy.deepcopy(frozen)))

    def test_adversary_leaves_original_evidence_untouched(self):
        frozen=fixture()
        original=a.checksum(frozen)
        out=a.analyze_frozen(frozen)
        self.assertEqual(original,a.checksum(frozen))
        self.assertEqual(out["source_sha256"],original)

    def test_all_registered_mutations_run(self):
        out=a.analyze_frozen(fixture())
        self.assertEqual(len(out["stress"]),11)
        self.assertEqual(sum(z["severity"]=="MILD" for z in out["stress"]),6)
        self.assertEqual(sum(z["severity"]=="HOSTILE" for z in out["stress"]),5)
        self.assertEqual(sum(z["error"] is not None for z in out["stress"]),0)
        self.assertTrue(all(isinstance(z["changed_roles"],list) and
                            isinstance(z["changed_quant_systems"],list)
                            for z in out["stress"]))

    def test_spread_attack_only_changes_quote_microstructure(self):
        f=fixture()
        stressed=a.mutate(f,"spread_plus_20bp")
        self.assertEqual(stressed["ticker"]["last"],f["ticker"]["last"])
        self.assertAlmostEqual(stressed["ticker"]["spread_bp"],22,delta=.005)
        self.assertEqual(f["ticker"]["spread_bp"],2)

    def test_book_fabrication_does_not_change_candle_history(self):
        f=fixture()
        stressed=a.mutate(f,"fake_bid_wall_x3")
        self.assertEqual(stressed["bars15"],f["bars15"])
        self.assertEqual(float(stressed["book"]["bids"][0][1]),
                         float(f["book"]["bids"][0][1])*3)
        self.assertEqual(float(stressed["book"]["asks"][0][1]),
                         float(f["book"]["asks"][0][1]))

    def test_trade_flip_mutates_recent_tape_only(self):
        f=fixture()
        stressed=a.mutate(f,"recent_trade_flip_10pct")
        altered=sum(x["side"]!=y["side"] for x,y in zip(f["trades"],stressed["trades"]))
        self.assertEqual(altered,8)
        self.assertEqual(stressed["book"],f["book"])

    def test_book_age_captures_original_not_wallclock(self):
        f=fixture()
        ok=a.replay_original(f)
        self.assertFalse(ok["agents"][0]["veto"])
        delayed=a.replay_original(a.mutate(f,"stale_book_150sec"))
        self.assertTrue(delayed["agents"][0]["veto"])
        self.assertEqual(delayed["signal"],"WAIT")

    def test_reject_unregistered_experiments(self):
        with self.assertRaises(ValueError):
            a.mutate(fixture(),"arbitrary_fake_outcome")

    def test_original_six_plus_seven_candidate_can_be_vetoed_by_stress(self):
        # Constructed SYNTHETIC bullish feed; never presented as actual market alpha.
        f=fixture()
        f["funding"]["fundingRate"]="-0.0008"
        f["mark"]["markPx"]="100.00"
        f["book"]["bids"]=[[x[0],str(float(x[1])*5),x[2],x[3]]
                           for x in f["book"]["bids"]]
        for t in f["trades"]:t["side"]="buy"
        self.assertEqual(a.replay_original(f)["signal"],"LONG")
        result=a.analyze_frozen(f)
        self.assertEqual(result["mild_changed_count"],0)
        stress={z["experiment"]:z for z in result["stress"]}
        self.assertEqual(stress["stale_book_150sec"]["result"]["signal"],"WAIT")
        self.assertEqual(stress["spread_plus_20bp"]["result"]["signal"],"WAIT")
        self.assertEqual(result["hostile_changed_count"],2)

    def test_exact_evidence_checksum_rejects_tampering(self):
        pkg={"schema":"quant2037-adversary-public-v1",
             "markets":[fixture()],"capture_errors":[]}
        pkg["evidence_sha256"]=a.checksum(pkg)
        self.assertTrue(a.verify_package(pkg))
        pkg["markets"][0]["ticker"]["last"]=199
        with self.assertRaisesRegex(ValueError,"checksum mismatch"):
            a.verify_package(pkg)

    def test_analysis_returns_no_trading_authority(self):
        pkg={"schema":"quant2037-adversary-public-v1",
             "markets":[fixture()],"capture_errors":[]}
        pkg["evidence_sha256"]=a.checksum(pkg)
        r=a.build_report(pkg)
        self.assertEqual(r["order_count"],0)
        self.assertFalse(r["nvidia_evaluated"])
        self.assertTrue(r["summary"]["not_validated_profit_edge"])
        self.assertEqual(r["summary"]["markets_evaluated"],1)

    def test_public_api_allowlist_does_not_call_private_endpoint(self):
        with self.assertRaises(ValueError):
            a.public_get("/api/v5/trade/order",{})

    def test_missing_derivatives_disables_candidate(self):
        f=fixture()
        f["missing_derivative_feeds"]=["funding"]
        self.assertEqual(a.replay_original(f)["signal"],"WAIT")
        self.assertIn("missing_or_unavailable_derivatives_data",
                      a.replay_original(f)["advanced_veto_reasons"])

    def test_real_order_api_not_in_allowed_endpoints(self):
        self.assertTrue(all(x.startswith("/api/v5/market/") or
                            x.startswith("/api/v5/public/")
                            for x in a.API_ALLOWLIST))
        self.assertFalse(any("trade/order" in x or "account" in x
                             for x in a.API_ALLOWLIST))

    def test_capture_market_fetches_only_public_feeds(self):
        f=fixture()
        names={"15m":f["bars15"],"1H":f["bars1h"],"4H":f["bars4h"]}
        called=[]
        def fake(path,params):
            called.append(path)
            if path=="/api/v5/market/candles":return names[params["bar"]]
            if path=="/api/v5/market/books":return [f["book"]]
            if path=="/api/v5/market/trades":return f["trades"]
            if path=="/api/v5/public/funding-rate":return [f["funding"]]
            if path=="/api/v5/public/open-interest":return [f["interest"]]
            if path=="/api/v5/public/mark-price":return [f["mark"]]
            raise AssertionError("Nonpublic")
        got=a.capture_market(f["ticker"],get=fake,clock_ms=MS)
        self.assertEqual(len(called),8)
        self.assertEqual(got["captured_at_ms"],MS)
        self.assertEqual(got["missing_derivative_feeds"],[])

if __name__=="__main__":
    unittest.main()
