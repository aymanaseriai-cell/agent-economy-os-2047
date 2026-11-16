import unittest
from trading.okx_target9_guard import check_target, usdt_equity
from trading.okx_live_executor import ExecutionBlocked

class Fake:
    def __init__(self,eq="4.53",positions=None,pending=None,uncertain=False):
        self.eq=eq;self.positions=positions or [];self.pending=pending or []
        self.uncertain=uncertain;self.posts=[]
    def request(self,method,path,*,params=None,body=None,auth=True):
        if path=="/api/v5/account/balance":
            return [{"totalEq":"500000","details":[{"ccy":"USDT","eq":self.eq}]}]
        if path=="/api/v5/account/config":return [{"posMode":"net_mode"}]
        if path=="/api/v5/account/positions":return self.positions
        if path=="/api/v5/trade/orders-pending":return self.pending
        if path=="/api/v5/trade/close-position":
            self.posts.append(body)
            if self.uncertain:raise ExecutionBlocked("unknown exchange outcome")
            self.positions=[p for p in self.positions if p["instId"]!=body["instId"]]
            self.eq="8.97"
            return [{"sCode":"0"}]
        raise AssertionError(path)

def pos(name="BTC-USDT-SWAP",mode="isolated",side="net"):
    return {"instId":name,"mgnMode":mode,"posSide":side,"pos":"2"}

class TargetTests(unittest.TestCase):
    def test_misleading_total_usd_does_not_trigger_nine_usdt(self):
        f=Fake();self.assertEqual(str(usdt_equity(f)),"4.53")
        self.assertEqual(check_target(f,close_armed=True),"BELOW_TARGET")
        self.assertFalse(f.posts)
    def test_at_nine_locks_even_if_flat(self):
        self.assertEqual(check_target(Fake(eq="9.00"),close_armed=True),"TARGET9_FLAT")
    def test_multiple_positions_close_and_verify_even_with_slippage(self):
        f=Fake(eq="9.2",positions=[pos(),pos("DOGE-USDT-SWAP")])
        self.assertEqual(check_target(f,close_armed=True),"TARGET9_FLAT")
        self.assertEqual(len(f.posts),2)
        self.assertTrue(all(x["autoCxl"] for x in f.posts))
        self.assertFalse(f.positions)
        self.assertEqual(f.eq,"8.97")
    def test_no_arm_no_writes(self):
        f=Fake(eq="9.1",positions=[pos()])
        with self.assertRaises(ExecutionBlocked):check_target(f)
        self.assertFalse(f.posts)
    def test_pending_order_blocks_writes(self):
        f=Fake(eq="9.1",positions=[pos()],pending=[{"instId":"BTC-USDT-SWAP"}])
        with self.assertRaises(ExecutionBlocked):check_target(f,close_armed=True)
        self.assertFalse(f.posts)
    def test_unsupported_exposure_blocks_writes(self):
        for bad in (pos(mode="cross"),pos(side="short"),pos(name="BTC-USD-SWAP")):
            f=Fake(eq="9.1",positions=[bad])
            with self.assertRaises(ExecutionBlocked):check_target(f,close_armed=True)
            self.assertFalse(f.posts)
    def test_unknown_exchange_close_not_retried(self):
        f=Fake(eq="10",positions=[pos()],uncertain=True)
        with self.assertRaises(ExecutionBlocked):check_target(f,close_armed=True)
        self.assertEqual(len(f.posts),1)
    def test_invalid_equity_is_rejected(self):
        for bad in ("NaN","Infinity","-1","bad"):
            with self.assertRaises(ExecutionBlocked):check_target(Fake(eq=bad),close_armed=True)

if __name__=="__main__":
    unittest.main()
