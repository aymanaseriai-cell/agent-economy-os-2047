import unittest
from datetime import datetime,timezone,timedelta
from trading.titan_survival_council import assess,review,AGENTS

def signal():
    return {
      "symbol":"ETH-USDT-SWAP","signal":"LONG","quote_price":100,
      "advanced_system_count":7,"advanced_confirmations":2,
      "advanced_veto_reasons":[],"derivatives_data_warnings":[],
      "omega_system_count":10,"omega_veto_reasons":[],"omega_rank_score":0.4,
      "agents":[{"evidence":{}} for _ in range(5)]+[
        {"evidence":{"indicative_stop_not_an_order":98,
                     "indicative_target_not_an_order":104}}],
      "omega_systems":[
        {"name":"04_exchange_digital_twin","evidence":{"estimated_round_trip_cost_bp":20}},
        {"name":"05_regime_mutation_detector","evidence":{"volatility_ratio":1.2}},
        {"name":"07_extreme_tail_risk","evidence":{
           "historical_lower_tail_mean_bp":-120,
           "historical_upper_tail_mean_bp":140}}]}

def report(s=None):
    return {"mode":"SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY",
            "market_scan_complete":True,"errors":[],
            "utc_timestamp":datetime.now(timezone.utc).isoformat(),
            "markets_analyzed":1,"results":[s or signal()]}

class SurvivalEightTest(unittest.TestCase):
    def test_paper_candidate_and_eight_agents(self):
        r=assess(signal())
        self.assertEqual(r["decision"],"PAPER_CANDIDATE_AWAITING_OUT_OF_SAMPLE_PROOF")
        self.assertEqual(len(r["agents"]),len(AGENTS))
        self.assertFalse(r["can_trade"])
    def test_capital_and_stop_caps(self):
        r=assess(signal())["risk_scenario"]
        self.assertGreaterEqual(r["proposed_leverage_x_research_only"],1)
        self.assertLessEqual(r["proposed_leverage_x_research_only"],8)
        self.assertLessEqual(r["proposed_margin_share_of_equity"],.20)
        self.assertLessEqual(r["planned_equity_loss_if_stop_fills"],.01)
        self.assertLessEqual(r["illustrative_stress_equity_loss"],.03)
    def test_no_live_ever(self):
        r=review(report())
        self.assertFalse(r["live_orders_permitted"])
        self.assertFalse(r["full_capital_investment_enforced"])
        self.assertFalse(r["guaranteed_to_avoid_liquidation"])
        self.assertEqual(r["real_orders_sent"],0)
    def test_fails_closed_on_stale(self):
        r=report()
        r["utc_timestamp"]=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
        with self.assertRaises(ValueError):review(r)
    def test_fails_closed_on_partial_scan(self):
        r=report();r["market_scan_complete"]=False
        with self.assertRaises(ValueError):review(r)
    def test_rejects_veto(self):
        s=signal();s["omega_veto_reasons"]=["risk"]
        self.assertEqual(assess(s)["decision"],"WAIT")
    def test_rejects_invalid_prices(self):
        s=signal();s["quote_price"]=float("nan")
        self.assertEqual(assess(s)["decision"],"WAIT")
    def test_rejects_missing_tail_data(self):
        s=signal();s["omega_systems"].pop()
        self.assertEqual(assess(s)["decision"],"WAIT")
    def test_shock_reduces_leverage(self):
        base=assess(signal())["risk_scenario"]["proposed_leverage_x_research_only"]
        s=signal()
        s["omega_systems"][-1]["evidence"]["historical_lower_tail_mean_bp"]=-300
        stressed=assess(s)["risk_scenario"]["proposed_leverage_x_research_only"]
        self.assertLess(stressed,base)
    def test_short_direction(self):
        s=signal();s["signal"]="SHORT"
        s["agents"][-1]["evidence"]={
          "indicative_stop_not_an_order":102,
          "indicative_target_not_an_order":96}
        self.assertEqual(assess(s)["decision"],"PAPER_CANDIDATE_AWAITING_OUT_OF_SAMPLE_PROOF")

if __name__=="__main__":
    unittest.main()
