import copy
import unittest
from datetime import datetime,timezone,timedelta
from trading.titan_portfolio_2037 import simulate,model_leverage,candidate

def sig(symbol="ETH-USDT-SWAP",direction="LONG",stop=98,rank=0.4):
    return {
      "symbol":symbol,"signal":direction,"quote_price":100,
      "advanced_system_count":7,"advanced_confirmations":2,
      "advanced_veto_reasons":[],"derivatives_data_warnings":[],
      "omega_system_count":10,"omega_veto_reasons":[],"omega_rank_score":rank,
      "agents":[{"evidence":{}} for _ in range(5)]+[
        {"evidence":{"indicative_stop_not_an_order":stop,
                     "indicative_target_not_an_order":104 if direction=="LONG" else 96}}],
      "omega_systems":[
        {"name":"04_exchange_digital_twin","evidence":{"estimated_round_trip_cost_bp":20}},
        {"name":"05_regime_mutation_detector","evidence":{"volatility_ratio":1.2}},
        {"name":"07_extreme_tail_risk","evidence":{
           "historical_lower_tail_mean_bp":-120,
           "historical_upper_tail_mean_bp":140}}]}
def rep(items=None):
    items=items if items is not None else [sig()]
    return {"mode":"SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY",
            "market_scan_complete":True,"errors":[],
            "utc_timestamp":datetime.now(timezone.utc).isoformat(),
            "markets_analyzed":len(items),"results":items}
class Titan2037Test(unittest.TestCase):
    def test_full_10_to_100_grid(self):
        result=simulate(rep())
        self.assertEqual(result["range_10x_to_100x_inclusive"],list(range(10,101)))
    def test_two_positions_full_capital_stress(self):
        r=simulate(rep([sig(),sig("BTC-USDT-SWAP","SHORT",100.5,.9)]),
                   margin_share=1.,max_positions=2)
        self.assertEqual(r["simulated_positions"],2)
        self.assertEqual(r["illustrative_margin_deployed_fraction_of_equity"],1.)
        self.assertEqual(len(r["positions"]),2)
        self.assertEqual(r["positions"][0]["symbol"],"BTC-USDT-SWAP")
    def test_dynamic_variable_leverage(self):
        tighter=model_leverage(.002,.002)
        wider=model_leverage(.02,.002)
        self.assertTrue(10<=wider<tighter<=100)
    def test_abstain_when_10x_fails(self):
        self.assertIsNone(model_leverage(.035,.004))
    def test_no_forced_entry_on_veto(self):
        bad=sig();bad["omega_veto_reasons"]=["risk"]
        r=simulate(rep([bad]))
        self.assertEqual(r["positions"],[])
        self.assertEqual(r["illustrative_margin_deployed_fraction_of_equity"],0.)
    def test_adverse_losses_monotonic(self):
        r=simulate(rep())
        losses=[x["illustrative_gross_linear_loss_fraction_of_equity"]
                for x in r["simultaneous_adverse_shock_stress"]]
        self.assertEqual(losses,sorted(losses))
    def test_never_live(self):
        r=simulate(rep())
        self.assertEqual(r["real_orders_placed"],0)
        self.assertEqual(r["live_leverage_changes"],0)
        self.assertFalse(r["live_trading_permitted"])
        self.assertFalse(r["full_capital_deployment_safe_for_live"])
        self.assertFalse(r["profits_or_no_liquidation_guaranteed"])
    def test_unknown_exchange_tier(self):
        r=simulate(rep())
        self.assertFalse(r["instrument_leverage_limits_verified"])
        self.assertFalse(r["positions"][0]["exchange_leverage_tier_verified"])
    def test_bad_margin_share(self):
        for value in (0,1.1,-.1,float("nan")):
            with self.subTest(value=value),self.assertRaises(ValueError):
                simulate(rep(),margin_share=value)
    def test_bad_slots(self):
        for value in (0,11,True):
            with self.subTest(value=value),self.assertRaises(ValueError):
                simulate(rep(),max_positions=value)
    def test_duplicate_symbol_rejected(self):
        with self.assertRaises(ValueError):
            simulate(rep([sig(),sig("ETH-USDT-SWAP","SHORT",101)]))
    def test_stale_report_rejected(self):
        p=rep()
        p["utc_timestamp"]=(datetime.now(timezone.utc)-
                            timedelta(hours=1)).isoformat()
        with self.assertRaises(ValueError):simulate(p)
    def test_invalid_signal_ignored(self):
        bad=sig();bad["omega_veto_reasons"]=["veto"]
        self.assertIsNone(candidate(bad))
    def test_short_and_long_both_supported(self):
        r=simulate(rep([sig(),sig("BTC-USDT-SWAP","SHORT",100.5,.9)]))
        self.assertEqual({p["direction"] for p in r["positions"]},{"LONG","SHORT"})
if __name__=="__main__":
    unittest.main()
