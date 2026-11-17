"""Regression and chronology checks for real OHLC historical H128 quantum study."""
import copy,math,unittest
from trading import titan_h128_quantum_history as r
from trading.edge_lab import BAR_MS

def bars(n=450):
    out=[];last=100.
    for i in range(n):
        c=100+i*.025+.15*math.sin(i/9)
        out.append({"ts":i*BAR_MS,"open":last,
                    "high":max(last,c)+.20,"low":min(last,c)-.20,"close":c})
        last=c
    return out

class H128Tests(unittest.TestCase):
    def test_actual_goal_and_fixed_policies(self):
        self.assertEqual((r.START,r.GOAL,r.RUIN),(4.15,9.462,.83))
        self.assertEqual(r.LEVERAGES,(3.,10.))
        self.assertGreaterEqual(len(r.UNIVERSE-r.PRIOR_MARKETS),6)
        self.assertIn("classical_same_features",r.POLICIES)
    def test_no_future_price_in_previous_signals(self):
        o=bars();a=r.signals(o);m=copy.deepcopy(o)
        m[-1]["close"]=m[-1]["high"]
        m[-1]["high"]*=1.1
        self.assertEqual(a,r.signals(m))
    def test_all_quantum_and_classical_signals_present(self):
        s=r.signals(bars())
        self.assertEqual(set(s),set(r.POLICIES))
    def test_insufficient_market_panel_cannot_pass(self):
        with self.assertRaises(ValueError):
            r.evaluate({"SUI-USDT-SWAP":bars()},{"SUI-USDT-SWAP":{}},{"SUI-USDT-SWAP":"h"})
    def test_no_order_endpoint_or_secret_lookup(self):
        from pathlib import Path
        s=(Path(__file__).parents[1]/"trading/titan_h128_quantum_history.py").read_text()
        self.assertNotIn("OKX_API_KEY",s)
        self.assertNotIn("/api/v5/trade/order",s)
        self.assertIn('"selected_on_training_only"',s)
if __name__=="__main__":unittest.main()
