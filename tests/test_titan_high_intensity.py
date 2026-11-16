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
