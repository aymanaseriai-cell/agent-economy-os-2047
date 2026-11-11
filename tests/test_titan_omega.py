import unittest
from trading.titan_omega import evaluate_omega, qubo_pick, SYSTEMS


def bars(n=200, trend=0.0002):
    p=100.0
    result=[]
    for i in range(n):
        p *= 1 + trend + (0.002 if i % 5 in (0, 1) else -0.0015)
        result.append({"ts": i * 900000, "open":p, "close":p,
                       "high":p * 1.002, "low":p * 0.998, "quote_vol":100000})
    return result


def case(direction="LONG", target=102.0, stop=99.0):
    return {"symbol":"BTC-USDT-SWAP","signal":direction,"quote_price":100.0,
            "agents":[{"evidence":{"indicative_stop_not_an_order":stop,
                                    "indicative_target_not_an_order":target}}]}


class OmegaResearchTests(unittest.TestCase):
    def setUp(self):
        self.bars=bars()
        self.ticker={"spread_bp":2.0}
        self.book={"bids":[["99.99","100"]],"asks":[["100.01","100"]]}
        self.trades=[{"side":"buy","sz":"1"},{"side":"sell","sz":"1"}]

    def run_omega(self, rec):
        return evaluate_omega(self.bars,self.bars,self.bars,self.book,self.trades,
                              self.ticker,{"fundingRate":"0"},{"oiUsd":"1000000"},
                              {"markPx":"100"},rec)

    def test_ten_systems_and_all_evidence_no_execution(self):
        x=self.run_omega(case())
        self.assertEqual(x["omega_system_count"],10)
        self.assertEqual([y["name"] for y in x["omega_systems"]],list(SYSTEMS))
        self.assertNotIn("api_key",str(x))
        self.assertTrue(x["omega_model_warning"])
        self.assertEqual(x["omega_systems"][9]["evidence"]["order_submitted"],False)

    def test_deterministic_bootstrap_and_scenario_count(self):
        x=self.run_omega(case())
        y=self.run_omega(case())
        self.assertEqual(x,y)
        self.assertEqual(x["omega_systems"][0]["evidence"]["paths"],384)

    def test_causal_claim_not_invented(self):
        x=self.run_omega(case())
        self.assertFalse(x["omega_systems"][5]["evidence"]["causal_inference_performed"])

    def test_adversarial_veto(self):
        self.trades=[{"side":"sell","sz":"100"}]
        x=self.run_omega(case())
        self.assertIn("adversarial_flow_or_funding_conflict",x["omega_veto_reasons"])
        self.assertEqual(x["omega_rank_score"],0.0)

    def test_bad_price_hypothesis_does_not_authorize_trade(self):
        x=self.run_omega(case(target=95.0,stop=99.0))
        self.assertEqual(x["omega_rank_score"],0.0)

    def test_insufficient_candles_fail_closed(self):
        self.bars=self.bars[:20]
        with self.assertRaises(ValueError):
            self.run_omega(case())

    def test_qubo_selects_fastest_positive_and_wait_allowed(self):
        def rec(symbol,score):
            return {"symbol":symbol,"signal":"LONG","omega_rank_score":score,
                    "omega_system_count":10,"omega_veto_reasons":[]}
        self.assertEqual(qubo_pick([rec("A",0.1),rec("B",0.4)]),"B")
        self.assertIsNone(qubo_pick([rec("A",0),rec("B",-0.3)]))
        self.assertIsNone(qubo_pick([{**rec("X",1),"omega_veto_reasons":["veto"]}]))

if __name__ == "__main__":
    unittest.main()
