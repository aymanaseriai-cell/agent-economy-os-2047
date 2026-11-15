import unittest
from decimal import Decimal
from unittest.mock import patch

from trading.microspot_scout import (cash_plan, closed_bars, floor_step,
                                      signal, scan, public_get)


class MicrospotTests(unittest.TestCase):
    def setUp(self):
        self.inst = {'instId': 'TEST-USDT', 'state': 'live',
                     'lotSz': '0.01', 'minSz': '0.1'}
        self.now_ms = 1_800_000_000_000
        self.bars = []
        for i in range(65):
            close = 100 + i * .2 if i < 64 else 120
            self.bars.append({
                'ts': self.now_ms - (65-i)*300_000,
                'open': close-.3, 'high': close+.2,
                'low': close-.6, 'close': close,
                'quote_vol': 100 if i < 64 else 600,
            })

    def test_9usd_feasibility(self):
        plan = cash_plan(Decimal('9'), Decimal('100'), self.inst)
        self.assertIsNone(plan)  # minimum 10 USDT even before fees
        plan = cash_plan(Decimal('9'), Decimal('1'), self.inst)
        self.assertIsNotNone(plan)
        self.assertEqual(plan['tdMode'], 'cash')
        self.assertLessEqual(Decimal(plan['paper_entry_cost_usdt']), Decimal('8.91'))
        self.assertFalse(plan['order_placed'])

    def test_round_down_lot_step(self):
        self.assertEqual(floor_step('3.779', '0.05'), Decimal('3.75'))
        with self.assertRaises(ValueError):
            floor_step('3', '0')

    def test_excludes_unconfirmed_candle(self):
        raw = []
        for b in reversed(self.bars):
            raw.append([str(b['ts']),str(b['open']),str(b['high']),
                        str(b['low']),str(b['close']),'1','1',
                        str(b['quote_vol']),'1'])
        spike = [str(self.now_ms),'1','9999','1','9999','1','1','90000','0']
        bars = closed_bars([spike]+raw)
        self.assertEqual(len(bars), 65)
        self.assertEqual(bars[-1]['close'], 120)
        self.assertEqual(bars[-1]['ts'], self.bars[-1]['ts'])

    def test_signal_is_past_data_and_fee_aware(self):
        result = signal(self.bars, '120.1', '120.0', now_ms=self.now_ms)
        self.assertEqual(result['signal'], 'BUY_WATCH_ONLY')
        self.assertGreater(result['modeled_roundtrip_cost_pct'], .5)
        self.assertGreater(result['illustrative_stop_distance_pct'], 0)

    def test_rejects_spread(self):
        self.assertIsNone(signal(self.bars, '121', '120', now_ms=self.now_ms))

    def test_rejects_stale_feed(self):
        self.assertIsNone(signal(self.bars, '120.1', '120.0',
                                 now_ms=self.now_ms + 60*60*1000))

    def test_rejects_no_breakout(self):
        bad = [dict(b) for b in self.bars]
        bad[-1]['close'] = 110
        self.assertIsNone(signal(bad, '110.1', '110', now_ms=self.now_ms))

    def test_no_orders_and_zero_private_calls(self):
        ticks = [{'instId': 'TEST-USDT', 'volCcy24h': '40000000',
                  'askPx': '1.1', 'bidPx': '1.099'}]
        def fake_get(path, params=None):
            if path.endswith('/tickers'):
                return ticks
            if path.endswith('/instruments'):
                return [self.inst]
            # Return valid but unqualified candles; this test checks only I/O safety.
            return [['1000000','1','1','1','1','1','1','1','1']]
        with patch('trading.microspot_scout.public_get', side_effect=fake_get) as caller:
            report = scan(equity=Decimal('9'))
        self.assertEqual(report['orders_sent'], 0)
        self.assertEqual(report['private_api_calls'], 0)
        self.assertEqual(report['screened_affordable_pairs'], 1)
        self.assertEqual(report['status'], 'NO_QUALIFIED_SIGNAL')
        self.assertTrue(all(call.args[0].startswith('/api/v5/market/') or
                            call.args[0] == '/api/v5/public/instruments'
                            for call in caller.call_args_list))

    def test_no_private_endpoints(self):
        with self.assertRaises(ValueError):
            public_get('/api/v5/trade/order')
        with self.assertRaises(ValueError):
            public_get('/api/v5/account/balance')


if __name__ == '__main__':
    unittest.main()
