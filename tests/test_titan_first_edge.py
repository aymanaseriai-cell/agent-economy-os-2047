"""FIRST EDGE — two-leg feasibility unit tests, purely synthetic fixtures."""
import unittest,inspect
from decimal import Decimal
from pathlib import Path
from trading import titan_first_edge_cash_carry as carry
from trading import titan_first_edge_sources as source

def instrument(coin,spot=True,minsz="0.01",lot="0.01",ctval="1"):
    data={"state":"live","minSz":minsz,"lotSz":lot}
    if not spot:data.update({"ctType":"linear","ctValCcy":coin,"ctVal":ctval})
    return data

def book(price,spot=True):
    return {"asks":[[str(price*1.001),"1000","0","0"]],
            "bids":[[str(price*.999),"1000","0","0"]]}

class EconomicFeasibility(unittest.TestCase):
    def test_goal_and_true_archive_category(self):
        self.assertEqual(source.ARCHIVE_MODULE_FUNDING,"3")
        self.assertEqual(source.ARCHIVE_MODULE_L2,"4")
        self.assertEqual(carry.BUDGET,Decimal("4.15"))
    def test_current_btc_minimum_blocks_small_account(self):
        spot=instrument("BTC",True,"0.00001","0.00000001")
        swap=instrument("BTC",False,"0.01","0.01","0.01")
        row=carry.limit_no_quote_guess({"coin":"BTC","spot":spot,"swap":swap},
                                      book(100000.),book(100000.))
        self.assertEqual(row["status"],"exact_base_delta_matched_quote_snapshot")
        self.assertEqual(row["exact_hedge_base_amount"],"0.0001")
        self.assertFalse(row["cost_scenarios"]["assumed_taker_5bp"]["fits_4_15_USDT"])
        self.assertGreater(row["cost_scenarios"]["assumed_taker_5bp"]
                           ["minimum_cash_USDT_excluding_extra_historical_tier_rules"],4.15)
    def test_smaller_hedge_is_arithmetically_possible(self):
        spot=instrument("ABC",True)
        swap=instrument("ABC",False)
        row=carry.limit_no_quote_guess({"coin":"ABC","spot":spot,"swap":swap},
                                     book(100.),book(100.))
        self.assertTrue(row["cost_scenarios"]["assumed_taker_5bp"]["fits_4_15_USDT"])
        self.assertEqual(row["spot_purchase_USDT"]>0,True)
        self.assertEqual(row["perp_contracts"],"0.01")
    def test_hedge_must_equal_base_units_not_just_notional(self):
        spot=instrument("ABC",True,"0.01","0.01")
        swap=instrument("ABC",False,"0.1","0.1","0.03")
        row=carry.limit_no_quote_guess({"coin":"ABC","spot":spot,"swap":swap},
                                     book(1.),book(1.))
        self.assertEqual(row["status"],"exact_base_delta_matched_quote_snapshot")
        self.assertEqual(Decimal(row["exact_hedge_base_amount"]),Decimal("0.03"))
        self.assertEqual(Decimal(row["perp_contracts"])*Decimal("0.03"),Decimal(row["exact_hedge_base_amount"]))
    def test_book_asks_and_bids_consume_visible_size(self):
        levels=[["100","1"],["101","2"]]
        self.assertEqual(carry.vwap_from_books(levels,Decimal("2")),Decimal("100.5"))
        self.assertIsNone(carry.vwap_from_books(levels,Decimal("5")))
    def test_stress_fee_increases_minimum_capital(self):
        spot=instrument("ABC",True)
        swap=instrument("ABC",False)
        row=carry.limit_no_quote_guess({"coin":"ABC","spot":spot,"swap":swap},
                                     book(100.),book(100.))
        self.assertGreater(
          row["cost_scenarios"]["assumed_taker_15bp"]["minimum_cash_USDT_excluding_extra_historical_tier_rules"],
          row["cost_scenarios"]["assumed_taker_5bp"]["minimum_cash_USDT_excluding_extra_historical_tier_rules"])
    def test_non_base_linear_swap_not_delta_neutral(self):
        spot=instrument("ABC",True)
        swap=instrument("ABC",False)
        swap["ctValCcy"]="USD"
        row=carry.limit_no_quote_guess({"coin":"ABC","spot":spot,"swap":swap},book(5.),book(5.))
        self.assertEqual(row["status"],"non_base_linear_swap_not_supported")
    def test_trust_rejects_forged_archive_url(self):
        with self.assertRaises(ValueError):
            source.safe_archive_zip("https://example.net/btc.zip")
    def test_no_real_order_endpoints(self):
        for code in (inspect.getsource(source),inspect.getsource(carry)):
            self.assertNotIn("/api/v5/trade/order",code)
            self.assertNotIn("OKX_API_KEY",code)
    def test_missing_orderbook_cannot_invent_hedge(self):
        spot=instrument("ABC",True);swap=instrument("ABC",False)
        x=carry.limit_no_quote_guess({"coin":"ABC","spot":spot,"swap":swap},
                     {"asks":[],"bids":[]},book(100.))
        self.assertEqual(x["status"],"incomplete_contract_or_orderbook")

if __name__=="__main__":unittest.main()
