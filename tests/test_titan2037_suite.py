import unittest
from trading.titan2037_suite import (
    BAR_MS, FEATURE_NAMES, SequencedBook, alpha_discovery, bundle,
    confirmed_bars, counterfactual, liquidation_defense, regime_brain,
    self_healing, shadow_exchange, smart_execution, thirty_second_router,
    trade_flow, truth_engine,
)

def bars(n=60):
    return [{"ts":i*BAR_MS,"confirmed":True,"open":100+i*.05,
             "high":101+i*.05,"low":99+i*.05,"close":100+i*.05} for i in range(n)]

class Titan2037Tests(unittest.TestCase):
    def test_counterfactual_gap_through_stop(self):
        x=counterfactual("LONG",100,99,105)
        self.assertLess(x["scenarios"][-1]["modeled_net"],x["scenarios"][0]["modeled_net"])
        with self.assertRaises(ValueError): counterfactual("SHORT",100,99,105)

    def test_orderbook_sequence_gap_atomic(self):
        b=SequencedBook()
        b.apply({"action":"snapshot","seqId":5,"ts":1000,
                 "bids":[["99","3"]],"asks":[["101","1"]]},now_ms=1000)
        with self.assertRaisesRegex(ValueError,"Sequence gap"):
            b.apply({"action":"update","seqId":7,"prevSeqId":6,"ts":1500,
                     "bids":[["99","4"]],"asks":[]},now_ms=1500)
        self.assertEqual(b.seq,5)
        b.apply({"action":"update","seqId":6,"prevSeqId":5,"ts":1600,
                 "bids":[["99","4"]],"asks":[]},now_ms=1600)
        self.assertEqual(b.seq,6)

    def test_orderflow_rejects_stale(self):
        b=SequencedBook()
        with self.assertRaises(ValueError):
            b.apply({"action":"snapshot","seqId":1,"ts":100,
                     "bids":[["98","2"]],"asks":[["99","2"]]},now_ms=20000)
        self.assertAlmostEqual(trade_flow([{"side":"buy","sz":3},
                                          {"side":"sell","sz":1}])["aggressor_imbalance"],.5)

    def test_shadow_stop_first(self):
        b=bars();b[2]["high"]=106;b[2]["low"]=97
        x=shadow_exchange({"published_ms":BAR_MS+1,"side":"LONG",
                           "stop":98,"target":105},b)
        self.assertEqual(x["orders"],0)
        self.assertEqual(x["outcome"],"stop_first")
        self.assertLess(x["modeled_net_fraction"],0)

    def test_shadow_future_unobserved(self):
        x=shadow_exchange({"published_ms":999*BAR_MS,"side":"LONG",
                           "stop":98,"target":105},bars())
        self.assertEqual(x["status"],"UNOBSERVED_NEXT_OPEN_NO_ORDER")

    def test_market_regime_verified_bars_only(self):
        self.assertIn(regime_brain(bars())["regime"],
                      {"VOLATILE_UNCERTAIN","TREND_UP","TREND_DOWN","RANGE"})
        data=bars();data[2]["confirmed"]=False
        with self.assertRaises(ValueError): regime_brain(data)
        with self.assertRaises(ValueError): confirmed_bars(bars()[:2])

    def test_purged_walkforward_is_never_live_approval(self):
        x=alpha_discovery({"a":[.01]*100,"b":[-.01]*100})
        self.assertFalse(x["approved_for_live"])
        self.assertGreater(len(x["folds"]),0)
        self.assertTrue(all(f["test_start"]>f["train_end"] for f in x["folds"]))

    def test_liquidation_stress(self):
        x=liquidation_defense([{"side":"LONG","notional_usdt":1000,
                               "leverage":100}],100)
        self.assertFalse(x["risk_gate"])
        self.assertFalse(x["exact_liquidation"])
        with self.assertRaises(ValueError):
            liquidation_defense([{"side":"SHORT","notional_usdt":1000,
                                  "leverage":101}],100)

    def test_paper_execution_only(self):
        x=smart_execution("LONG",99.99,100.01,20000,100,50)
        self.assertEqual(x["status"],"PAPER_PLAN_ONLY")
        self.assertEqual(x["orders"],0)
        self.assertEqual(smart_execution("LONG",99,101,20000,100,1)["status"],"COST_DEPTH_VETO")

    def test_30_second_verified_cooldown(self):
        h=[{"type":"2","ts":100000}]
        self.assertFalse(thirty_second_router(h,129999,True)["eligible"])
        self.assertTrue(thirty_second_router(h,130000,True)["eligible"])
        self.assertFalse(thirty_second_router(h,130000,False)["eligible"])

    def test_never_auto_retry_unknown_private_order(self):
        self.assertEqual(self_healing("PRIVATE_POST_ORDER","50026",1)["action"],
                         "HALT_RECONCILE_EXCHANGE")
        self.assertEqual(self_healing("PUBLIC_GET","50026",1)["delay_seconds"],5)
        self.assertEqual(self_healing("PUBLIC_GET","50026",4)["action"],"OPEN_CIRCUIT")

    def test_truth_net_signed_fees(self):
        x=truth_engine([{"trade_id":"a","realized_pnl_usdt":"4",
                         "fee_usdt":"-0.5"}],
                       [{"event_id":"f","amount_usdt":"-0.2"}])
        self.assertEqual(x["net_realized_from_import"],"3.3")
        self.assertFalse(x["verified_against_private_OKX"])
        with self.assertRaises(ValueError):
            truth_engine([{"trade_id":"a","realized_pnl_usdt":"4","fee_usdt":"-0.5"}]*2,[])

    def test_ten_missing_data_not_fabricated(self):
        x=bundle({})
        self.assertEqual(set(x["features"]),set(FEATURE_NAMES))
        self.assertEqual(x["orders"],0)
        self.assertFalse(x["live_trading_reenabled"])
        self.assertTrue(all(v["status"]=="NEEDS_DATA_NOT_CONNECTED"
                            for v in x["features"].values()))

    def test_some_offline_evidence(self):
        x=bundle({"counterfactual":{"side":"LONG","entry":100,"stop":99,"target":105},
                  "recovery":{"operation":"PUBLIC_GET","code":"50026","failures":1}})
        self.assertEqual(x["features"]["counterfactual"]["status"],"EVALUATED")
        self.assertEqual(x["features"]["self_healing"]["status"],"EVALUATED")
        self.assertEqual(x["features"]["truth_engine"]["status"],"NEEDS_DATA_NOT_CONNECTED")

    def test_no_private_order_routes(self):
        import inspect
        import trading.titan2037_suite as suite
        source=inspect.getsource(suite)
        for signature in ("/api/v5/trade/order","OKX_API_KEY","OKX_SECRET_KEY",
                          "urlopen(","subprocess.run("):
            self.assertNotIn(signature,source)
if __name__=="__main__": unittest.main()
