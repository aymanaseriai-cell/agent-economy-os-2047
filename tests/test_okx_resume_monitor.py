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

class PortfolioCapacityMonitorTests(unittest.TestCase):
    def test_existing_protected_position_allows_other_market(self):
        from unittest.mock import patch
        from decimal import Decimal
        snap={'symbols':frozenset({'BTC-USDT-SWAP'}),
              'total':Decimal('1000'),'free':Decimal('800'),
              'planned':Decimal('20'),'notional':Decimal('2000')}
        with patch('trading.okx_portfolio_guard.snapshot',return_value=snap):
            self.assertEqual(inspect_account_state(FakeOKX(),max_positions=2),
                             'PORTFOLIO_ELIGIBLE')

    def test_two_positions_wait_for_exit(self):
        from unittest.mock import patch
        with patch('trading.okx_portfolio_guard.snapshot',
                   return_value={'symbols':frozenset({'BTC-USDT-SWAP','ETH-USDT-SWAP'})}):
            self.assertEqual(inspect_account_state(FakeOKX(),max_positions=2),
                             'POSITION_OPEN_PROTECTED')

    def test_nine_protected_positions_leave_one_available(self):
        from unittest.mock import patch
        from decimal import Decimal
        symbols=frozenset(f"ALT{i}-USDT-SWAP" for i in range(9))
        snap={'symbols':symbols,'total':Decimal('1000'),
              'free':Decimal('800'),'planned':Decimal('5'),
              'notional':Decimal('1000')}
        with patch('trading.okx_portfolio_guard.snapshot',return_value=snap):
            self.assertEqual(inspect_account_state(FakeOKX(),max_positions=10),
                             'PORTFOLIO_ELIGIBLE')

    def test_ten_positions_are_monitored_without_new_entry(self):
        from unittest.mock import patch
        symbols=frozenset(f"ALT{i}-USDT-SWAP" for i in range(10))
        with patch('trading.okx_portfolio_guard.snapshot',
                   return_value={'symbols':symbols}):
            self.assertEqual(inspect_account_state(FakeOKX(),max_positions=10),
                             'POSITION_OPEN_PROTECTED')

    def test_monitor_blocks_more_than_ten(self):
        with self.assertRaisesRegex(ExecutionBlocked,'Invalid portfolio capacity'):
            inspect_account_state(FakeOKX(),max_positions=11)

class ExplicitOpenPositionSlotTests(unittest.TestCase):
    def test_one_held_slot_still_allows_second_through_tenth(self):
        from unittest.mock import patch
        from decimal import Decimal
        state={'symbols':frozenset({'BTC-USDT-SWAP'}),
               'total':Decimal('1000'),'free':Decimal('800'),
               'planned':Decimal('10'),'notional':Decimal('1000')}
        with patch('trading.okx_portfolio_guard.snapshot',return_value=state),\
             patch('builtins.print') as printer:
            status=inspect_account_state(FakeOKX(),max_positions=10)
        self.assertEqual(status,'PORTFOLIO_ELIGIBLE')
        self.assertTrue(any('open=1 limit=10 remaining=9' in c.args[0]
                            for c in printer.call_args_list))

    def test_tenth_slot_is_hard_capacity_gate(self):
        from unittest.mock import patch
        symbols=frozenset(f"ALT{i}-USDT-SWAP" for i in range(10))
        with patch('trading.okx_portfolio_guard.snapshot',
                   return_value={'symbols':symbols}),\
             patch('builtins.print') as printer:
            status=inspect_account_state(FakeOKX(),max_positions=10)
        self.assertEqual(status,'POSITION_OPEN_PROTECTED')
        self.assertTrue(any('open=10 limit=10 remaining=0' in c.args[0]
                            for c in printer.call_args_list))
