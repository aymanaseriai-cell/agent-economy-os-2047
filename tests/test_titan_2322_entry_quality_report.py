"""Historical regression of a READ-ONLY stricter candidate filter."""
import unittest
from trading.titan_2322_entry_quality_report import evaluate_candidate,audit_report

def row(side):
    is_long=side=="LONG"
    return {
        "symbol":"INJ-USDT-SWAP" if is_long else "ARB-USDT-SWAP",
        "signal":side,
        "advanced_confirmations":1,
        "advanced_contradictions":1 if is_long else 0,
        "advanced_veto_reasons":[],
        "omega_veto_reasons":[],
        "derivatives_data_warnings":[],
        "omega_system_count":10,
        "omega_rank_score":2.71980473 if is_long else 1.76237954,
        "ordinal_buy_points":3 if is_long else 0,
        "ordinal_sell_points":0 if is_long else 3,
        "num_bullish_agents":2 if is_long else 0,
        "num_bearish_agents":0 if is_long else 2,
        "speed_matrix_rank_factor":1.067596 if is_long else 1.226676,
        "quote_price":"6.884" if is_long else ".13075",
        "omega_systems":[{"name":"04_exchange_digital_twin","evidence":{
           "estimated_round_trip_cost_bp":17.45 if is_long else 16.77}}],
        "agents":[{"agent":"01_liquidity_sentinel","evidence":{
           "turnover_usdt_est":22984215 if is_long else 18115038,
           "spread_bp":1.453 if is_long else .765,
           "orderbook_age_sec":.9,
           "bid_depth_contracts_20_levels":591894 if is_long else 30214.4,
           "ask_depth_contracts_20_levels":152859 if is_long else 27210.5,
        }}]+[{}]*4+[{"evidence":{
           "indicative_stop_not_an_order":"6.809" if is_long else ".13243",
           "indicative_target_not_an_order":"7.1" if is_long else ".12757",
        }}],
    }

class TestReadOnlyStrictCandidates(unittest.TestCase):
    def test_historical_long_and_short_remain_possible(self):
        self.assertEqual(evaluate_candidate(row("LONG")),[])
        self.assertEqual(evaluate_candidate(row("SHORT")),[])
        report={"results":[row("LONG"),row("SHORT")]}
        self.assertEqual([x["quality_status"] for x in audit_report(report)],["PASS","PASS"])

    def test_strict_rejects_weaker_conditions(self):
        q=row("LONG");q["omega_rank_score"]=.5
        self.assertIn("OMEGA_RANK_LT_1_5",evaluate_candidate(q))
        q=row("SHORT");q["agents"][0]["evidence"]["spread_bp"]=9
        self.assertIn("SPREAD_GT_8BP",evaluate_candidate(q))
        q=row("LONG");q["advanced_contradictions"]=2
        self.assertIn("QUANT_CONTRADICTIONS",evaluate_candidate(q))
        q=row("LONG");q["agents"][0]["evidence"]["orderbook_age_sec"]=90
        self.assertIn("BOOK_STALE",evaluate_candidate(q))

    def test_no_trade_permission_on_wait(self):
        q=row("LONG");q["signal"]="WAIT"
        self.assertEqual(evaluate_candidate(q),["NO_LONG_OR_SHORT"])
        self.assertEqual(audit_report({"results":[q]}),[])

if __name__=="__main__":
    unittest.main()
