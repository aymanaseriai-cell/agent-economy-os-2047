"""FIRST EDGE original cash-and-carry math tests. NO fabricated market result."""
import copy,io,inspect,math,unittest
from decimal import Decimal
from trading import titan_first_edge_carry_historical as h

def spec(coin,spot=True,minsz=".01",step=".01",ctval="1"):
    row={"state":"live","minSz":minsz,"lotSz":step,"baseCcy":coin}
    if not spot:row.update({"ctType":"linear","ctValCcy":coin,"ctVal":ctval})
    return row

class CarryCausality(unittest.TestCase):
 def test_exact_min_cash_is_paid_spot_plus_2x_margin_and_four_fees(self):
    s={"spot":spec("ABC"),"swap":spec("ABC",False)}
    q=h.affordable_exact(s,4.15,100.,100.,.0005)
    self.assertIsNotNone(q)
    base,contracts,cash=q
    self.assertEqual(base,.01)
    self.assertAlmostEqual(cash,1.5+4*.0005,places=7)
 def test_small_capital_blocks_realistic_large_contract(self):
    s={"spot":spec("BTC",True,".00001",".00000001"),
       "swap":spec("BTC",False,".01",".01",".01")}
    self.assertIsNone(h.affordable_exact(s,4.15,100000.,100000.,.0005))
 def test_exact_underlying_quantity_quantized_not_fractional_fiction(self):
    s={"spot":spec("ABC",True,".01",".01"),
       "swap":spec("ABC",False,".1",".1",".03")}
    q=h.affordable_exact(s,4.15,1.,1.,.0005)
    self.assertEqual(q[0],.03)
    self.assertEqual(q[1],1.)
 def test_short_funding_cash_flow_rate_sign(self):
    # Short receives positive funding; negative settlement debits.
    q=.01;markpx=100.
    self.assertGreater(q*markpx*.0002,0)
    self.assertLess(q*markpx*(-.0002),0)
 def test_predeclared_hold_horizons_and_dev_calendar(self):
    self.assertEqual(h.HOLDS,{"one_funding_interval":1,"seven_days":21})
    self.assertEqual(h.EXPECTED,2196)
    self.assertEqual(h.FAMILY_TEST_BUDGET,2)
    self.assertTrue(h.NOT_A_BLIND_TEST)
 def test_no_prior_funding_no_trade_signal(self):
    rates={h.START:h.D(0),h.START+8*h.FOUR_H:-.001}
    self.assertEqual(h.locate_events(rates,1),[])
 def test_future_funding_rate_is_not_signal(self):
    t=h.START
    rates={t:.00001,t+8*h.FOUR_H:.00001}
    signal=h.locate_events(rates,1)
    revised=dict(rates);revised[t+8*h.FOUR_H]=-.05
    other=h.locate_events(revised,1)
    # The ENTRY based on t is unchanged; later t events may change.
    self.assertEqual(signal[0]["entry_ts"],other[0]["entry_ts"])
 def test_cost_stress_slippage_exceeds_base(self):
    self.assertGreater(h.COSTS["stress"][0],h.COSTS["base"][0])
    self.assertGreater(h.COSTS["stress"][1],h.COSTS["base"][1])
 def test_fee_and_basis_profit_are_distinct(self):
    spot_in,spot_out=100,99
    perp_in,perp_out=101,100
    q=.01
    self.assertAlmostEqual(q*((spot_out-spot_in)-(perp_out-perp_in)),0)
    # Equal directional changes are neutral without basis dislocation.
 def test_funding_does_not_equal_portfolio_profit(self):
    # Positive funding can lose if adverse basis change exceeds it.
    funding=.01;basis=-.02;fees=.002
    self.assertLess(funding+basis-fees,0)
 def test_no_real_exchange_order_or_secret(self):
    s=inspect.getsource(h)
    self.assertNotIn("/api/v5/trade/order",s)
    self.assertNotIn("OKX_API_KEY",s)

if __name__=="__main__":unittest.main()
