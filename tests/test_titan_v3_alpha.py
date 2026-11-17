"""V3 independent causal and false-profit guard tests; synthetic fixtures only."""
import copy,hashlib,math,unittest
from trading import titan_v3_alpha_discovery as a
from trading import titan_v3_research as r
from trading.edge_lab import BAR_MS

def fake_bars(n=16*85):
    price=100.;out=[]
    for i in range(n):
        close=100+i*.01+.1*math.sin(i/17)
        out.append({"ts":i*BAR_MS,"open":price,"close":close,
                    "high":max(price,close)+.2,"low":min(price,close)-.2,
                    "vol_quote":100000.+100*(i%13)})
        price=close
    return out

class V3Independent(unittest.TestCase):
    def test_target_and_8_predeclared_economic_families(self):
        self.assertEqual((r.START,r.TARGET),(4.15,1037504.15))
        self.assertEqual(len(a.HYPOTHESES),8)
        self.assertEqual(r.MARKETS,8)
        self.assertLessEqual(r.CAPITAL_MARGIN_MAX,.2)
        self.assertLessEqual(r.STOP_EQUITY_RISK_MAX,.04)
    def test_cannot_read_last_incomplete_4h_bar(self):
        bars=fake_bars();extra=copy.deepcopy(bars)
        extra.append({"ts":bars[-1]["ts"]+BAR_MS,"open":1.,
                      "close":900.,"high":1000.,"low":.1,
                      "vol_quote":1e12})
        self.assertEqual(a._bar_4h(bars),a._bar_4h(extra))
    def test_cross_market_timestamp_misalignment_fails(self):
        bars=fake_bars();syms=["FET","FLOW","RLC","KAVA","TWT","QTUM"]
        panel={s+"-USDT-SWAP":bars for s in syms}
        self.assertTrue(a.observations(panel))
        bad=copy.deepcopy(panel)
        for bar in bad["FET-USDT-SWAP"]:
            bar["ts"]+=16*BAR_MS
        with self.assertRaises(ValueError):a.observations(bad)
    def test_holm_adjustments_not_smaller_than_unadjusted(self):
        p={"a":.01,"b":.04,"c":.3}
        adj=a.holm(p)
        self.assertEqual(adj["a"],.03)
        self.assertTrue(all(adj[k]>=p[k] for k in p))
    def test_final_future_labels_can_never_change_train_dev_fit(self):
        x=[]
        for t in range(1100):
            idx=t*16
            feats={k:float((t%9)-4)/2 for k in a.HYPOTHESES}
            feats.update({"simple_momentum":1.,"always_flat":0.})
            x.append({"future_idx":idx+16,"i":idx,"ts":t*4*3600000,
                      "future_y":math.sin(t)*.001,"features":feats})
        first=a.frozen_discovery(x,10000,10300,16000)
        altered=copy.deepcopy(x)
        for row in altered:
            if row["i"]>=16000:row["future_y"]=1000000.
        self.assertEqual(first,a.frozen_discovery(altered,10000,10300,16000))
    def test_temporal_purging_before_final(self):
        parts=r.windows(20159)
        self.assertLess(parts["train"][1],parts["development"][0])
        self.assertLess(parts["development"][1],parts["final_1"][0])
        self.assertLess(parts["final_1"][1],parts["final_2"][0])
        self.assertLess(parts["final_2"][1],parts["final_3"][0])
    def test_small_account_rejects_unaffordable_contract(self):
        spec={"instId":"RLC-USDT-SWAP","ctVal":"100","lotSz":"1",
              "minSz":"1","ctValCcy":"RLC"}
        self.assertEqual(r.affordable(spec,4.15,100.,.5,3.,.2),(0.,0.))
    def test_approximate_execution_next_15m_open_only(self):
        name="RLC-USDT-SWAP";bars=fake_bars()
        spec={"instId":name,"ctVal":"1","lotSz":".01",
              "minSz":".01","ctValCcy":"RLC"}
        x=r.simulated_trade(bars,(40,1,.4,.1,.2),spec,[],
                            4.15,3.,.0005,.0003,len(bars))
        self.assertTrue(x is None or
           (x["entry_ts"]==bars[41]["ts"] and
            x["eq_after"]>=0 and x["margin"]<=.201*4.15))
    def test_real_volume_limit_blocks_fantasy_liquidity(self):
        name="RLC-USDT-SWAP";bars=fake_bars()
        for item in bars:item["vol_quote"]=1.
        specs={name:{"instId":name,"ctVal":"1","lotSz":".01",
                    "minSz":".01","ctValCcy":"RLC"}}
        x=r.replay({name:bars},specs,{name:[]},
                   {name:[(40,1,.4,.1,.2)]},3.,30,200,.0005,.0003)
        self.assertEqual(x["trades"],0)
        self.assertGreater(x["rejected_volume"],0)
    def test_abstention_not_fake_profit(self):
        name="RLC-USDT-SWAP"
        x=r.replay({name:fake_bars()},{name:{"instId":name}},
                   {name:[]},{},3.,30,200,.0005,.0003)
        self.assertEqual(x["equity"],4.15)
        self.assertEqual(x["trades"],0)
    def test_empty_frozen_market_refused(self):
        with self.assertRaises(ValueError):r.evaluate({}, {}, {}, {})
    def test_no_auth_and_no_real_order_route(self):
        from pathlib import Path
        for name in ("titan_v3_alpha_discovery.py","titan_v3_research.py"):
            s=(Path(__file__).parents[1]/"trading"/name).read_text()
            self.assertNotIn("/api/v5/trade/order",s)
            self.assertNotIn("OKX_API_KEY",s)
        self.assertEqual(r.sha(b"alpha"),hashlib.sha256(b"alpha").hexdigest())
if __name__=="__main__":unittest.main()
