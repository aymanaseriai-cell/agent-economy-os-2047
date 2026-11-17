import copy
import inspect
import math
import unittest

from trading import titan_omega_infinite12 as engine
from trading import titan_omega_infinite12_audit as auditor
from trading import titan_omega_infinite12_models as models


def candles(n=137, growth=0.001):
    out=[]
    for j in range(n):
        p=100.0*math.exp(growth*j)
        out.append({"ts":j*engine.CANDLE_MS,"open":p,"high":p*1.001,
             "low":p*0.999,"close":p*math.exp(growth*0.5),"quote":100_000_000.0})
    return out


def spec():
    return {"instId":"SOL-USDT-SWAP","state":"live","ctType":"linear",
            "ctValCcy":"SOL","minSz":"0.01","lotSz":"0.01","ctVal":"0.01","lever":"50"}


class TestInfinite12(unittest.TestCase):
    def test_model_unitarity(self):
        b=candles()
        self.assertIn(models.quantum_walk_interference(b,35),(-1,0,1))

    def test_four_unique_models(self):
        self.assertEqual(len(models.STRATEGIES),4)
        self.assertEqual(len(set(models.STRATEGIES.values())),4)

    def test_no_future_signal(self):
        b=candles()
        before=[f(b,45) for f in models.STRATEGIES.values()]
        b[46]["close"]*=1.20
        b[47]["close"]*=.75
        self.assertEqual(before,[f(b,45) for f in models.STRATEGIES.values()])

    def test_insufficient_warmup(self):
        with self.assertRaises(ValueError):
            models.classical_momentum(candles(),12)

    def test_contract_metadata_fail_closed(self):
        s=spec();del s["lever"]
        result=engine.simulate(candles(),s,[],models.NAMES[0],33,"ordinary")
        self.assertEqual(result["status"],"UNVERIFIED_CONTRACT_SPEC")
        self.assertFalse(result["trades"])

    def test_fee_cases(self):
        self.assertGreater(engine.COSTS["stress"]["taker"],engine.COSTS["ordinary"]["taker"])

    def test_lot_rounding(self):
        q=engine.contracts(4.15,100,1e9,10,(.01,.01,.01,50))
        self.assertGreater(q,0)
        self.assertAlmostEqual(q/.01,round(q/.01))

    def test_time_horizon(self):
        r=engine.simulate(candles(),spec(),[],models.NAMES[0],33,"ordinary")
        self.assertEqual(r["end_ts"]-r["start_ts"],12*60*60*1000)

    def test_real_order_api_absent(self):
        src=inspect.getsource(engine)
        self.assertNotIn("/api/v5/trade/order",src)
        self.assertNotIn("api_key=",src.lower())
        self.assertNotIn("requests.post(",src.lower())

    def test_source_hash_tamper(self):
        raw={"declared_symbols":list(engine.SYMBOLS),"real_orders":0,"markets":{}}
        raw["seal_sha256"]=engine.digest(raw)
        raw["real_orders"]=1
        with self.assertRaises(ValueError):
            engine.evaluate(raw)

    def test_closed_equity_and_ledger_audit(self):
        b=candles()
        report=engine.simulate(b,spec(),[],models.NAMES[0],33,"ordinary")
        self.assertLessEqual(len(report["trades"]),48)
        data={"seal_sha256":"", "real_orders":0,"markets":{
             "SOL-USDT-SWAP":{"bars":b,"funding":[],"spec":spec(),
                 "bar_sha256":engine.digest(b),"funding_sha256":engine.digest([]),
                 "spec_sha256":engine.digest(spec())}}}
        data["seal_sha256"]=engine.digest({k:v for k,v in data.items() if k!="seal_sha256"})
        w=dict(report,symbol="SOL-USDT-SWAP")
        key=models.NAMES[0]+"/ordinary"
        summary={key:{"windows":1,"filled_trades":len(w["trades"]),
           "target_hit_windows":int(w["end_equity"]>=8.3),
           "liquidation_proxy_events":w["liquidations"]}}
        a={"source_seal_sha256":data["seal_sha256"],"real_orders":0,
           "scientific_verdict":"NO_NEW_INDEPENDENT_OUT_OF_SAMPLE_PROOF",
           "best_independent_net_pct":None,"windows":[w],"summary":summary}
        result=auditor.audit(data,a)
        self.assertEqual(result["status"],"PASS",str(result["errors"]))
        if w["trades"]:
            a2=copy.deepcopy(a)
            a2["windows"][0]["trades"][0]["fees_usdt"]+=1
            self.assertEqual(auditor.audit(data,a2)["status"],"FAIL")

    def test_no_unjustified_independent_return(self):
        self.assertEqual(engine.START_USDT,4.15)
        self.assertEqual(engine.TARGET_USDT,8.30)
        self.assertEqual(engine.WINDOW_BARS,48)


if __name__=="__main__":
    unittest.main()
