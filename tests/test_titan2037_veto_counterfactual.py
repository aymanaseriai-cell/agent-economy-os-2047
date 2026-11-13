import inspect
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import json
from trading.shadow_observatory import BAR_MS, sha, utc_ms
from trading.titan2037_veto_counterfactual import AGENTS, evaluate, read_snapshots

BASE = utc_ms("2026-11-01T00:00:00Z")

def stamp(t):
    return datetime.fromtimestamp(t/1000, tz=timezone.utc).isoformat().replace("+00:00","Z")

def snapshot(t=BASE, core="LONG", side="WAIT", policy="policy-A",
             symbol="TEST-USDT-SWAP", **change):
    decision = {
        "symbol":symbol, "decision":side, "core_before_filters":core,
        "last_complete_15m_candle_ms":t-BAR_MS,
        "advanced_veto_reasons":["no_independent_quant_confirmation"],
        "derivatives_data_warnings":[], "role_votes":[],
        "stop":98 if core=="LONG" else 102,
        "target":105 if core=="LONG" else 95,
    }
    decision.update(change)
    data={"schema":"quant2037-shadow-v1","mode":"PUBLIC_ONLY_NO_TRADES",
          "timestamp_utc":stamp(t),"decision_policy_sha256":policy,
          "decisions":[decision],"errors":[]}
    data["snapshot_sha256"]=sha(data)
    return data

def bars(first=BASE,n=60,close=101):
    return [{"ts":first+i*BAR_MS,"open":100,"high":102,"low":99,
             "close":close,"quote_vol":10000} for i in range(n)]

class TestVetoCounterfactual(unittest.TestCase):
    def test_original_wait_hypothetical_only(self):
        a=evaluate([snapshot()],{"TEST-USDT-SWAP":bars()},BASE+60*BAR_MS)
        self.assertEqual(a["summary"]["primary_matured_counterfactuals"],1)
        self.assertEqual(a["summary"]["status"],"INSUFFICIENT_PROSPECTIVE_OUTCOMES")
        self.assertEqual(a["episodes"][0]["original_action"],"WAIT")
        self.assertEqual(a["episodes"][0]["hypothetical_side"],"LONG")
        self.assertTrue(a["episodes"][0]["hypothetical_only"])
        self.assertEqual(a["orders_placed"],0)
        self.assertFalse(a["trading_allowed"])
        self.assertEqual(len(a["agents"]),len(AGENTS))

    def test_costs_stressed_not_relabelled_as_profits(self):
        a=evaluate([snapshot()],{"TEST-USDT-SWAP":bars()},BASE+60*BAR_MS)["episodes"][0]
        self.assertGreater(a["one_hour_net_bp"],a["double_cost_net_bp"])
        self.assertGreater(a["double_cost_net_bp"],a["stress_net_bp"])

    def test_core_wait_does_not_fabricate_direction(self):
        a=evaluate([snapshot(core="WAIT")],{},BASE+60*BAR_MS)
        self.assertEqual(a["summary"]["directional_rejected_checked"],0)
        self.assertEqual(a["episodes"],[])

    def test_bad_snapshot_digest(self):
        a=snapshot()
        a["timestamp_utc"]="2026-11-02T00:00:00Z"
        with self.assertRaises(ValueError):
            evaluate([a],{"TEST-USDT-SWAP":bars()},BASE+60*BAR_MS)

    def test_future_archive(self):
        with self.assertRaisesRegex(ValueError,"Future"):
            evaluate([snapshot(BASE+100*BAR_MS)],{},BASE+60*BAR_MS)

    def test_source_candle_not_closed(self):
        s=snapshot(last_complete_15m_candle_ms=BASE)
        with self.assertRaisesRegex(ValueError,"future source candle"):
            evaluate([s],{"TEST-USDT-SWAP":bars()},BASE+60*BAR_MS)

    def test_missing_prices_not_profit(self):
        a=evaluate([snapshot()],{},BASE+60*BAR_MS)
        self.assertEqual(a["summary"]["missing_prices"],1)
        self.assertEqual(a["summary"]["primary_matured_counterfactuals"],0)

    def test_immature_price_horizon(self):
        a=evaluate([snapshot()],{"TEST-USDT-SWAP":bars(n=2)},BASE+60*BAR_MS)
        self.assertEqual(a["summary"]["immature_or_protection_invalid"],1)
        self.assertEqual(a["episodes"],[])

    def test_missing_stop_not_imputed(self):
        a=evaluate([snapshot(stop=None)],{"TEST-USDT-SWAP":bars()},BASE+60*BAR_MS)
        self.assertEqual(a["summary"]["immature_or_protection_invalid"],1)

    def test_dedup_identical_snapshot(self):
        s=snapshot()
        a=evaluate([s,s],{"TEST-USDT-SWAP":bars()},BASE+60*BAR_MS)
        self.assertEqual(a["summary"]["archived_snapshots"],1)

    def test_same_symbol_inside_four_hours_excluded(self):
        a=evaluate([snapshot(),snapshot(BASE+BAR_MS)],
                   {"TEST-USDT-SWAP":bars()},BASE+60*BAR_MS)
        self.assertEqual(a["summary"]["primary_matured_counterfactuals"],1)
        self.assertEqual(a["summary"]["correlated_repeats_excluded"],1)

    def test_source_policy_isolation(self):
        a=evaluate([snapshot(),snapshot(BASE+4*BAR_MS,policy="policy-B")],
                   {"TEST-USDT-SWAP":bars()},BASE+60*BAR_MS)
        self.assertEqual(a["summary"]["other_policy_versions_excluded"],1)
        self.assertEqual(a["summary"]["primary_matured_counterfactuals"],1)

    def test_short_counterfactual(self):
        a=evaluate([snapshot(core="SHORT")],
                   {"TEST-USDT-SWAP":bars(close=99)},BASE+60*BAR_MS)
        self.assertEqual(a["summary"]["primary_matured_counterfactuals"],1)
        self.assertEqual(a["episodes"][0]["hypothetical_side"],"SHORT")

    def test_archive_loader_verifies_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"s1"
            p.mkdir()
            (p/"quant2037_snapshot.json").write_text(json.dumps(snapshot()))
            self.assertEqual(len(read_snapshots(d)),1)

    def test_no_order_routes(self):
        import trading.titan2037_veto_counterfactual as m
        source=inspect.getsource(m)
        for forbidden in ("OKX_API_KEY","OKX_SECRET_KEY",
                          "/api/v5/trade/order","requests.post(",
                          "subprocess.run(","place_order("):
            self.assertNotIn(forbidden,source)

if __name__=="__main__":
    unittest.main()
