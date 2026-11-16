import unittest
from decimal import Decimal
from trading.okx_live_executor import (
    contract_size, check_mode, OpportunityRiskRejected,
    MARGIN_99_MODE, FULL_MARGIN_ARM, MODE_ARM, choose_signal,
)
from trading.titan_speed_matrix import evaluate_speed_matrix


def candles(n=80, trend=0.0004):
    out = []
    price = 100.0
    for i in range(n):
        price *= 1 + trend
        out.append({"open": price - 0.1, "close": price,
                    "high": price + 0.2, "low": price - 0.2})
    return out


class TITAN99Margin(unittest.TestCase):
    def setUp(self):
        self.inst = {"ctVal": "1", "minSz": "1", "lotSz": "1"}

    def test_99pct_margin_exact_target_for_20x(self):
        q = contract_size(self.inst, 100, 1000, ".005",
                          capital_mode=MARGIN_99_MODE,
                          exchange_max=500, leverage=20)
        self.assertEqual(q, Decimal("198"))
        self.assertEqual((q * 100) / (1000 * 20), Decimal(".99"))

    def test_99pct_margin_respects_exchange_ceiling_and_lot(self):
        self.assertEqual(contract_size(self.inst,100,1000,".005",
                          capital_mode=MARGIN_99_MODE,
                          exchange_max=7,leverage=20),Decimal("7"))

    def test_99pct_planned_stop_is_not_guaranteed_loss_cap(self):
        # Max 99% estimated equity-at-stop; actual liquidation may be earlier.
        q = contract_size(self.inst,100,1000,".05",
                          capital_mode=MARGIN_99_MODE,
                          exchange_max=500,leverage=20)
        self.assertEqual(q, Decimal("198"))
        with self.assertRaises(OpportunityRiskRejected):
            contract_size(self.inst,100,1000,".05001",
                          capital_mode=MARGIN_99_MODE,
                          exchange_max=500,leverage=20)

    def test_separately_armed_high_margin(self):
        env = {"OKX_EXECUTION_ARM": MODE_ARM["demo"],
               "OKX_CAPITAL_MODE": MARGIN_99_MODE,
               "OKX_API_KEY":"test","OKX_SECRET_KEY":"test","OKX_PASSPHRASE":"test"}
        with self.assertRaisesRegex(Exception, "armed"):
            check_mode("demo", env)
        env["OKX_FULL_MARGIN_ARM"] = FULL_MARGIN_ARM
        check_mode("demo", env)

    def test_no_exchange_size_fails(self):
        with self.assertRaisesRegex(Exception, "fresh OKX max-size"):
            contract_size(self.inst,100,1000,".01",
                          capital_mode=MARGIN_99_MODE)


class TITANSpeedMatrix(unittest.TestCase):
    def setUp(self):
        self.up = candles()
        self.down = candles(trend=-.0004)
        self.book = {"bids":[["100","300"]],"asks":[["101","100"]]}
        self.tape = [{"side":"buy","sz":"200"},{"side":"sell","sz":"50"}]

    def test_ranked_alignment_favors_uptrend_long(self):
        a = evaluate_speed_matrix(self.up,self.up,self.up,self.book,self.tape,
                                  {"signal":"LONG"})
        b = evaluate_speed_matrix(self.down,self.down,self.down,self.book,self.tape,
                                  {"signal":"LONG"})
        self.assertEqual(a["speed_matrix_status"],"RANK_ONLY")
        self.assertGreater(a["speed_matrix_rank_factor"],b["speed_matrix_rank_factor"])
        self.assertFalse(a["speed_matrix_live_permission"])

    def test_invalid_book_is_neutral_not_order(self):
        a = evaluate_speed_matrix(self.up,self.up,self.up,{},self.tape,{"signal":"LONG"})
        self.assertEqual(a["speed_matrix_status"],"INVALID_PUBLIC_DATA")
        self.assertEqual(a["speed_matrix_rank_factor"],1.0)

    def test_wait_never_trades(self):
        a = evaluate_speed_matrix(self.up,self.up,self.up,self.book,self.tape,{"signal":"WAIT"})
        self.assertEqual(a["speed_matrix_status"],"WAIT")
        self.assertFalse(a["speed_matrix_live_permission"])

    def test_invalid_speed_factor_cannot_select(self):
        import time
        now=int(time.time()*1000)
        candidate={"symbol":"UNI-USDT-SWAP","quote_price":100,
                  "signal":"LONG","last_complete_15m_candle_ms":now-16*60*1000,
                  "advanced_system_count":7,"advanced_confirmations":2,
                  "advanced_veto_reasons":[],"derivatives_data_warnings":[],
                  "execution":"DISABLED","order_count":0,"ordinal_buy_points":5,
                  "ordinal_sell_points":0,"agents":[{"evidence":{}}]*5+
                    [{"evidence":{"indicative_stop_not_an_order":98,
                                  "indicative_target_not_an_order":104}}],
                  "omega_system_count":10,"omega_rank_score":1.5,
                  "omega_veto_reasons":[],"speed_matrix_rank_factor":"NaN"}
        self.assertIsNone(choose_signal({"results":[candidate]}))

    def test_matrix_cannot_override_omega_veto(self):
        import time
        now=int(time.time()*1000)
        rec={"symbol":"UNI-USDT-SWAP","quote_price":100,
             "signal":"LONG","last_complete_15m_candle_ms":now-16*60*1000,
             "advanced_system_count":7,"advanced_confirmations":1,
             "advanced_veto_reasons":[],"derivatives_data_warnings":[],
             "execution":"DISABLED","order_count":0,
             "ordinal_buy_points":4,"ordinal_sell_points":0,
             "agents":[{"evidence":{}}]*5+[{"evidence":{
                "indicative_stop_not_an_order":98,
                "indicative_target_not_an_order":104}}],
             "omega_system_count":10,"omega_rank_score":1,
             "omega_veto_reasons":["funding_conflict"],
             "speed_matrix_rank_factor":1.5}
        self.assertIsNone(choose_signal({"results":[rec]}))


if __name__ == "__main__":
    unittest.main()


class ExtremeMargin9999Tests(unittest.TestCase):
    """Model-only tests: no exchange orders, no guaranteed equity-loss limit."""

    def setUp(self):
        self.inst = {"ctVal": "1", "lotSz": "1", "minSz": "1"}

    def test_exact_9999_percent_when_contract_precision_allows(self):
        from trading.okx_live_executor import MARGIN_9999_MODE
        q = contract_size(self.inst, 1, 1000, ".001",
                          capital_mode=MARGIN_9999_MODE, exchange_max=50000, leverage=20)
        self.assertEqual(q, Decimal("19998"))
        self.assertEqual(q/Decimal("20")/Decimal("1000"), Decimal("0.9999"))

    def test_exchange_capacity_can_reduce_allocation(self):
        from trading.okx_live_executor import MARGIN_9999_MODE
        q = contract_size(self.inst, 1, 1000, ".001",
                          capital_mode=MARGIN_9999_MODE, exchange_max=103, leverage=100)
        self.assertEqual(q, Decimal("103"))

    def test_stop_risk_veto_survives(self):
        from trading.okx_live_executor import MARGIN_9999_MODE
        with self.assertRaises(OpportunityRiskRejected):
            contract_size(self.inst, 1, 1000, ".1",
                          capital_mode=MARGIN_9999_MODE, exchange_max=100000, leverage=20)

    def test_separately_armed_single_position(self):
        from trading.okx_live_executor import MARGIN_9999_MODE
        env={"OKX_EXECUTION_ARM":MODE_ARM["demo"],
             "OKX_CAPITAL_MODE":MARGIN_9999_MODE, "OKX_MAX_ACTIVE_POSITIONS":"1",
             "OKX_API_KEY":"test","OKX_SECRET_KEY":"test","OKX_PASSPHRASE":"test"}
        with self.assertRaisesRegex(Exception,"separately armed"):
            check_mode("demo",env)
        env["OKX_FULL_MARGIN_ARM"]=FULL_MARGIN_ARM
        check_mode("demo",env)
        env["OKX_MAX_ACTIVE_POSITIONS"]="2"
        with self.assertRaisesRegex(Exception,"Multi-position"):
            check_mode("demo",env)

    def test_missing_exchange_max_size_refuses(self):
        from trading.okx_live_executor import MARGIN_9999_MODE
        with self.assertRaisesRegex(Exception,"fresh OKX max-size"):
            contract_size(self.inst,1,1000,".001",capital_mode=MARGIN_9999_MODE)


class TITANStrictExtremeTests(unittest.TestCase):
    """New opt-in live gates only veto, never promote weak signals."""

    def setUp(self):
        import time
        self.now=int(time.time()*1000)
        self.candidate={
            "symbol":"UNI-USDT-SWAP", "signal":"LONG", "quote_price":"100",
            "last_complete_15m_candle_ms":self.now-16*60_000,
            "advanced_system_count":7,"advanced_confirmations":2,
            "advanced_contradictions":0,"advanced_veto_reasons":[],
            "derivatives_data_warnings":[],
            "ordinal_buy_points":5,"ordinal_sell_points":0,
            "num_bullish_agents":3,"num_bearish_agents":0,
            "agents":[{"agent":"01_liquidity_sentinel","evidence":{
                "turnover_usdt_est":35000000,"spread_bp":5,
                "orderbook_age_sec":2,
                "bid_depth_contracts_20_levels":100,
                "ask_depth_contracts_20_levels":100}}]+[{"agent":"other","evidence":{}}]*4+
                [{"agent":"06_risk_marshal","evidence":{
                    "indicative_stop_not_an_order":"98",
                    "indicative_target_not_an_order":"106"}}],
            "execution":"DISABLED","order_count":0,
            "omega_system_count":10,"omega_veto_reasons":[],"omega_rank_score":"2",
            "omega_estimated_time_to_target_minutes":30,
            "omega_target_hit_fraction_null_model":"0.5"
        }

    def test_strong_candidate_passes_strict(self):
        from trading.okx_live_executor import choose_signal
        self.assertIs(choose_signal({"results":[self.candidate]},now_ms=self.now,strict=True),self.candidate)

    def test_each_weakness_fails_strict(self):
        from trading.okx_live_executor import choose_signal
        from copy import deepcopy
        for field,value in [("advanced_confirmations",1),("advanced_contradictions",1),
                            ("num_bullish_agents",2),("ordinal_buy_points",3),
                            ("omega_system_count",9),("omega_veto_reasons",["veto"])]:
            c=deepcopy(self.candidate);c[field]=value
            with self.subTest(field=field):
                self.assertIsNone(choose_signal({"results":[c]},now_ms=self.now,strict=True))
        for field,value in [("turnover_usdt_est",29000000),("spread_bp",9),
                            ("orderbook_age_sec",31),("ask_depth_contracts_20_levels",0)]:
            c=deepcopy(self.candidate);c["agents"][0]["evidence"][field]=value
            with self.subTest(field=field):
                self.assertIsNone(choose_signal({"results":[c]},now_ms=self.now,strict=True))
        c=deepcopy(self.candidate);c["agents"][-1]["evidence"]["indicative_target_not_an_order"]="103"
        self.assertIsNone(choose_signal({"results":[c]},now_ms=self.now,strict=True))

    def test_standard_mode_still_accepts_less_strict_candidate(self):
        from trading.okx_live_executor import choose_signal
        from copy import deepcopy
        c=deepcopy(self.candidate);c["advanced_confirmations"]=1
        self.assertIs(choose_signal({"results":[c]},now_ms=self.now,strict=False),c)

    def test_exact_99999pct_margin_fraction_and_arm(self):
        from trading.okx_live_executor import contract_size, MARGIN_99999_MODE
        inst={"ctVal":"1","lotSz":"1","minSz":"1"}
        q=contract_size(inst,1,100000,".001",
                        capital_mode=MARGIN_99999_MODE,exchange_max=3000000,leverage=20)
        self.assertEqual(q,Decimal("1999980"))
        self.assertEqual(q/Decimal(20)/Decimal(100000),Decimal("0.99999"))
        env={"OKX_EXECUTION_ARM":MODE_ARM["demo"],
             "OKX_CAPITAL_MODE":MARGIN_99999_MODE,"OKX_ENTRY_PROFILE":"strict_extreme",
             "OKX_API_KEY":"test","OKX_SECRET_KEY":"test","OKX_PASSPHRASE":"test"}
        with self.assertRaisesRegex(Exception,"separately armed"):
            check_mode("demo",env)
        env["OKX_FULL_MARGIN_ARM"]=FULL_MARGIN_ARM
        check_mode("demo",env)
