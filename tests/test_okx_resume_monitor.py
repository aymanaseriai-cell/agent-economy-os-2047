"""Read-only auto-reentry state checks, including exchange-side 10m cooldown."""
import unittest
from trading.okx_resume_monitor import inspect_account_state
from trading.okx_live_executor import ExecutionBlocked


class FakeOKX:
    def __init__(self, *, positions=None, pending=None, algos=None, history=None):
        self.positions=[] if positions is None else positions
        self.pending=[] if pending is None else pending
        self.algos={} if algos is None else algos
        self.history=[] if history is None else history
        self.calls=[]
    def request(self, method, path, params=None, body=None):
        self.calls.append((method,path))
        if method!="GET" or body is not None:
            raise AssertionError("Monitor must never place or modify orders")
        if path=="/api/v5/account/config": return [{"posMode":"net_mode"}]
        if path=="/api/v5/account/positions": return self.positions
        if path=="/api/v5/trade/orders-pending": return self.pending
        if path=="/api/v5/trade/orders-algo-pending":
            return self.algos.get(params["ordType"],[])
        if path=="/api/v5/account/positions-history": return self.history
        raise AssertionError(path)


class ResumeMonitorTests(unittest.TestCase):
    def test_flat_no_history_eligible(self):
        c=FakeOKX()
        self.assertEqual(inspect_account_state(c),"FLAT_ELIGIBLE")
        self.assertTrue(all(m=="GET" for m,_ in c.calls))

    def test_protected_position_monitor_only(self):
        c=FakeOKX(positions=[{"pos":"1","instId":"BTC-USDT-SWAP"}],
                  algos={"oco":[{"instId":"BTC-USDT-SWAP",
                                 "slTriggerPx":"90","tpTriggerPx":"110"}]})
        self.assertEqual(inspect_account_state(c),"POSITION_OPEN_PROTECTED")
        self.assertFalse(any("/positions-history" in p for _,p in c.calls))

    def test_unprotected_position_never_treated_as_ready(self):
        c=FakeOKX(positions=[{"pos":"1","instId":"BTC-USDT-SWAP"}])
        with self.assertRaisesRegex(ExecutionBlocked,"TP/SL"):
            inspect_account_state(c)

    def test_pending_order_is_ambiguous(self):
        c=FakeOKX(pending=[{"instId":"BTC-USDT-SWAP"}])
        with self.assertRaisesRegex(ExecutionBlocked,"pending"):
            inspect_account_state(c)

    def test_flat_but_orphaned_algo_fails_closed(self):
        c=FakeOKX(algos={"oco":[{"instId":"BTC-USDT-SWAP",
                                 "slTriggerPx":"90","tpTriggerPx":"110"}]})
        with self.assertRaisesRegex(ExecutionBlocked,"orphaned"):
            inspect_account_state(c)

    def test_multiple_positions_fail_closed(self):
        c=FakeOKX(positions=[{"pos":"1","instId":"BTC-USDT-SWAP"},
                             {"pos":"1","instId":"ETH-USDT-SWAP"}])
        with self.assertRaisesRegex(ExecutionBlocked,"multiple"):
            inspect_account_state(c)

    def test_recent_exchange_close_forces_cooldown(self):
        import time
        now=int(time.time()*1000)
        c=FakeOKX(history=[{"instType":"SWAP","type":"2",
                            "uTime":str(now-2000)}])
        self.assertEqual(inspect_account_state(c),"COOLDOWN_ACTIVE")

    def test_expired_cooldown_allows_new_scan(self):
        import time
        now=int(time.time()*1000)
        c=FakeOKX(history=[{"instType":"SWAP","type":"2",
                            "uTime":str(now-11*60*1000)}])
        self.assertEqual(inspect_account_state(c),"FLAT_ELIGIBLE")

    def test_bad_cooldown_history_blocks(self):
        c=FakeOKX(history=[{"instType":"SWAP","type":"2","uTime":"bad"}])
        with self.assertRaises(ExecutionBlocked):
            inspect_account_state(c)


if __name__=="__main__":
    unittest.main()
