import copy
import math
import unittest
from trading import titan_omega24 as e
from trading import titan_omega24_audit as a
from trading import titan_omega_infinite12 as old


def candles(n=350, slope=.0007):
    rows=[]
    for i in range(n):
        p=100*math.exp(i*slope)
        rows.append(dict(ts=i*900000,open=p,high=p*1.006,low=p*.994,
                         close=p*math.exp(.5*slope),quote=1e8))
    return rows


def spec():
    return dict(instId="SOL-USDT-SWAP",state="live",ctType="linear",
                ctValCcy="SOL",minSz=".01",lotSz=".01",ctVal=".01",lever="50")


def source():
    b=candles()
    markets={}
    for s in e.SYMBOLS:
        r=dict(bars=b,spec=dict(spec(),instId=s),funding=[])
        r["bar_sha256"]=old.digest(r["bars"])
        r["spec_sha256"]=old.digest(r["spec"])
        r["funding_sha256"]=old.digest(r["funding"])
        markets[s]=r
    d=dict(declared_symbols=list(e.SYMBOLS),real_orders=0,markets=markets)
    d["seal_sha256"]=old.digest(d)
    return d


class Omega24Tests(unittest.TestCase):
    def test_new_hamiltonian_norm_and_signal(self):
        self.assertIn(e.causal_hamiltonian_phasewalk(candles(),45),(-1,0,1))
    def test_genuine_model_comparators(self):
        self.assertEqual(len(e.STRATEGIES),3)
        self.assertEqual(len(set(e.STRATEGIES.values())),3)
    def test_no_future_mutation(self):
        b=candles()
        p=[fn(b,45) for fn in e.STRATEGIES.values()]
        b[46]["close"]*=.5;b[47]["close"]*=1.5
        self.assertEqual(p,[fn(b,45) for fn in e.STRATEGIES.values()])
    def test_24h_windows_and_no_partial(self):
        r=e.evaluate(source())
        self.assertTrue(r["windows"])
        self.assertTrue(all(x["end_ts"]-x["start_ts"]==24*3600_000 for x in r["windows"]))
        self.assertEqual(r["window_bars"],96)
        self.assertFalse(r["fresh_independent_prospective"])
        self.assertIsNone(r["independent_hit_rate"])
    def test_min_contract_fail_closed(self):
        bad=spec();bad.pop("lever")
        r=e.simulate(candles(),bad,[],"classical_momentum",33,"stress")
        self.assertFalse(r["feasible"])
        self.assertEqual(r["end_equity"],4.15)
    def test_full_independent_ledger_audit(self):
        d=source();r=e.evaluate(d)
        checked=a.audit(d,r)
        self.assertEqual(checked["status"],"PASS",checked["errors"])
        self.assertEqual(checked["windows_checked"],len(r["windows"]))
    def test_fee_tampering_rejected(self):
        d=source();r=e.evaluate(d)
        fills=[t for w in r["windows"] for t in w["trades"]]
        self.assertTrue(fills)
        fills[0]["fee"]+=1
        self.assertEqual(a.audit(d,r)["status"],"FAIL")
    def test_window_cherry_pick_rejected(self):
        d=source();r=e.evaluate(d)
        r["windows"].pop()
        self.assertEqual(a.audit(d,r)["status"],"FAIL")
    def test_source_sha_rejected(self):
        d=source();d["markets"][e.SYMBOLS[0]]["bars"][10]["close"]*=1.1
        with self.assertRaises(ValueError):e.evaluate(d)
    def test_no_live_execution_api(self):
        import inspect
        s=inspect.getsource(e)+inspect.getsource(a)
        for bad in ("OKX_API_KEY","/api/v5/trade/order","requests.post("):
            self.assertNotIn(bad,s)
    def test_funding_and_margin_consistency(self):
        r=e.simulate(candles(),spec(),[],"classical_momentum",33,"ordinary")
        for t in r["trades"]:
            self.assertLessEqual(t["margin"],.25001*t["equity_before"])
            self.assertGreaterEqual(t["fee"],0.)
            self.assertLessEqual(t["lev"],100)
    def test_stress_fees_higher(self):
        self.assertGreater(e.COSTS["stress"]["taker"],e.COSTS["ordinary"]["taker"])
        self.assertGreater(e.COSTS["stress"]["spread_slip"],e.COSTS["ordinary"]["spread_slip"])


if __name__=="__main__":unittest.main()
