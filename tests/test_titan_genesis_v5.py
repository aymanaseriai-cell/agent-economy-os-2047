"""TITAN GENESIS V5: synthetic unit fixtures NEVER support profit claims."""
import math,unittest,copy
from trading import titan_genesis_v5 as v

class GenesisV5(unittest.TestCase):
 def test_target(self):
  self.assertEqual((v.START,v.GOAL),(4.15,1037504.15))
  self.assertEqual(len(v.HYPOTHESES),3)
 def test_breakeven_cost(self):
  self.assertAlmostEqual(v.cost_one("base"),.00185)
  self.assertAlmostEqual(v.cost_one("stress"),.00925)
 def test_no_future_labels_in_direction(self):
  prev={"ts":v.FOUR_H,"high":101.,"low":99.,"close":100.,"quote":10000.}
  future={"ts":v.FOUR_H*2,"open":100.,"close":101.}
  x=v.build_event("ETH-USDT-SWAP",1,prev,future,1,"leader_laggard_spillover")
  opposite=dict(future,close=90.)
  y=v.build_event("ETH-USDT-SWAP",1,prev,opposite,1,"leader_laggard_spillover")
  self.assertEqual(x["side"],y["side"])
  self.assertNotEqual(x["gross_log_return"],y["gross_log_return"])
 def test_holm(self):
  p={"a":.01,"b":.04,"c":.8}
  adj=v.holm(p)
  self.assertEqual(adj["a"],.03)
  self.assertTrue(all(adj[k]>=p[k] for k in p))
 def test_no_statistical_power_3months(self):
  samples=[{"month":f"2026-{i+1:02d}","gross_log_return":.02} for i in range(3)]
  self.assertEqual(v.signflip_month_p(samples,"base"),1.)
 def test_bootstrap_deterministic(self):
  x=[{"month":f"2024-{i+1:02d}","gross_log_return":.01} for i in range(12)]
  self.assertEqual(v.month_bootstrap(x,.001,100),v.month_bootstrap(x,.001,100))
 def test_calibration_lower_bound(self):
  self.assertIsNone(v.wilson_lower(0,0))
  self.assertLess(v.wilson_lower(8,10),.8)
  self.assertEqual(v.wilson_lower(0,10),0.)
 def test_minlot_cannot_be_forged(self):
  spec={"ctVal":"100","lotSz":"1","minSz":"1"}
  self.assertEqual(v.size_contract(spec,4.15,100.,.01),(0.,0.))
 def test_quantized_contract_margin(self):
  spec={"ctVal":"1","lotSz":".01","minSz":".01"}
  q,notional=v.size_contract(spec,4.15,1.,.005)
  self.assertGreater(q,0)
  self.assertLessEqual(notional/v.LEVERAGE,4.15*v.MARGIN+1e-8)
 def test_thin_volume_must_abstain(self):
  spec={"AB-USDT-SWAP":{"ctVal":"1","lotSz":".01","minSz":".01"}}
  x={"symbol":"AB-USDT-SWAP","entry_ts":v.FOUR_H*2,"signal_ts":v.FOUR_H,
     "side":1,"prior_range_pct":.01,"prior_quote_volume":1.,
     "next_open":1.,"next_close":2.}
  result=v.paper([x],{},spec,"base")
  self.assertEqual(result["trades"],0)
  self.assertEqual(result["end_usdt"],4.15)
  self.assertGreater(result["rejections"].get("quote_liquidity",0),0)
 def test_closed_equity_and_one_position(self):
  spec={"AB-USDT-SWAP":{"ctVal":"1","lotSz":".01","minSz":".01"}}
  events=[{"symbol":"AB-USDT-SWAP","entry_ts":(i+2)*v.FOUR_H,
           "signal_ts":(i+1)*v.FOUR_H,"side":1,
           "prior_range_pct":.005,"prior_quote_volume":100000,
           "next_open":1.,"next_close":1.01} for i in range(5)]
  out=v.paper(events,{},spec,"base")
  self.assertEqual(out["trades"],5)
  for a,b in zip(out["ledger"],out["ledger"][1:]):
   self.assertAlmostEqual(a["equity_after"],b["equity_before"])
   self.assertGreaterEqual(b["entry_ts"],a["entry_ts"]+v.FOUR_H)
 def test_ruin_unknown_no_trades(self):
  self.assertIsNone(v.simple_ruin([]))
 def test_sha_detects_true_candle_edit(self):
  self.assertNotEqual(v.digest(b"101.2"),v.digest(b"102.2"))
 def test_no_private_orders(self):
  from pathlib import Path
  code=(Path(__file__).parents[1]/"trading"/"titan_genesis_v5.py").read_text()
  self.assertNotIn("/api/v5/trade/order",code)
  self.assertNotIn("OKX_API_KEY",code)

if __name__=="__main__":unittest.main()
