import os
import unittest
from decimal import Decimal
from unittest.mock import patch
from trading.okx_spot_live import (SpotHalt, OKXCash, entry_body, protect_body,
                                    price_step, no_derivatives_or_open_orders, execute, fmt)


class MockClient:
    def __init__(self, positions=None, pending=None):
        self.positions = positions if positions is not None else []
        self.pending = pending if pending is not None else []
        self.requests = []

    def request(self, method, path, *, params=None, body=None):
        self.requests.append((method, path, params, body))
        if path.endswith('/positions'):
            return self.positions
        if 'orders-' in path:
            return self.pending
        raise AssertionError('unexpected endpoint')


class SpotLiveTests(unittest.TestCase):
    def test_entry_uses_cash_spot_quote_notional(self):
        b = entry_body('ABC-USDT', Decimal('7.56'), 'TMSabcdef')
        self.assertEqual(b['tdMode'], 'cash')
        self.assertEqual(b['tgtCcy'], 'quote_ccy')
        self.assertEqual(b['side'], 'buy')
        self.assertEqual(b['sz'], '7.56')
        self.assertNotIn('lever', b)

    def test_non_spot_entry_refused(self):
        with self.assertRaises(SpotHalt):
            entry_body('ABC-USDT-SWAP', Decimal('6'), 'id')

    def test_protection_is_oco_sell_and_rounded(self):
        b = protect_body('ABC-USDT', Decimal('5.678'), Decimal('100'),
                         Decimal('0.05'), Decimal('0.01'), 'TMPO123')
        self.assertEqual(b['ordType'], 'oco')
        self.assertEqual(b['side'], 'sell')
        self.assertEqual(b['tdMode'], 'cash')
        self.assertEqual(b['sz'], '5.67')
        self.assertEqual(b['slTriggerPx'], '98')
        self.assertEqual(b['tpTriggerPx'], '105')

    def test_derivative_open_position_blocks_before_orders(self):
        x = MockClient(positions=[{'instId':'BTC-USDT-SWAP', 'pos':'1'}])
        with self.assertRaises(SpotHalt):
            no_derivatives_or_open_orders(x)
        self.assertFalse(any(m=='POST' for m,_,_,_ in x.requests))

    def test_pending_order_blocks_before_orders(self):
        x = MockClient(pending=[{'ordId':'111'}])
        with self.assertRaises(SpotHalt):
            no_derivatives_or_open_orders(x)
        self.assertFalse(any(m=='POST' for m,_,_,_ in x.requests))

    def test_endpoint_write_allowlist_cash_only(self):
        env = {'OKX_API_KEY':'test','OKX_SECRET_KEY':'test','OKX_PASSPHRASE':'test'}
        client = OKXCash(env)
        with self.assertRaises(SpotHalt):
            client.request('POST', '/api/v5/trade/order',
                           body={'instId':'BTC-USDT-SWAP','tdMode':'isolated','side':'buy','ordType':'market','tgtCcy':'quote_ccy'})
        with self.assertRaises(SpotHalt):
            client.request('POST', '/api/v5/trade/order-algo',
                           body={'instId':'BTC-USDT','tdMode':'cash','side':'buy','ordType':'oco'})
        with self.assertRaises(SpotHalt):
            client.request('POST', '/api/v5/account/set-leverage', body={'instId':'BTC-USDT','tdMode':'cash'})

    def test_real_mode_requires_spot_arm(self):
        env = {'OKX_API_KEY':'test', 'OKX_SECRET_KEY':'test','OKX_PASSPHRASE':'test'}
        with patch('trading.okx_spot_live.no_derivatives_or_open_orders'),\
             patch('trading.okx_spot_live.available', return_value=Decimal('9')):
            with self.assertRaises(SpotHalt):
                execute(env, mode='live')

    def test_verify_does_not_trade(self):
        env = {'OKX_API_KEY':'test', 'OKX_SECRET_KEY':'test','OKX_PASSPHRASE':'test'}
        with patch('trading.okx_spot_live.no_derivatives_or_open_orders'),\
             patch('trading.okx_spot_live.available', return_value=Decimal('9')):
            self.assertIn('READ-ONLY',execute(env,mode='verify'))

    def test_price_rounding(self):
        self.assertEqual(price_step('100.123','0.05',up=True),Decimal('100.15'))
        self.assertEqual(price_step('100.123','0.05',up=False),Decimal('100.10'))

    def test_unknown_api_write_error_is_halt_not_retry(self):
        # POST must not be attempted outside the explicit controller path.
        with self.assertRaises(SpotHalt):
            OKXCash({'OKX_API_KEY':'key','OKX_SECRET_KEY':'s','OKX_PASSPHRASE':'p',
                     'OKX_API_DOMAIN':'https://attacker.invalid'})

if __name__ == '__main__':
    unittest.main()


class LivePathTests(unittest.TestCase):
    def test_live_submits_exactly_one_cash_buy_and_one_protective_oco(self):
        import trading.okx_spot_live as m
        sent = []
        class Fake:
            def __init__(self, env): pass
            def request(self, method, path, *, params=None, body=None):
                if method == 'POST':
                    sent.append((path, body))
                return []
        env = {'OKX_API_KEY':'k','OKX_SECRET_KEY':'s','OKX_PASSPHRASE':'p',
               'OKX_EXECUTION_MODE':'live','OKX_ENABLE_REAL_TRADING':'YES',
               'OKX_SPOT_LIVE_ARM':'I_AUTHORIZE_REAL_CASH_SPOT_LOSS'}
        candidate={'symbol':'TEST-USDT','last_closed_bar_close':1}
        with patch.object(m,'OKXCash',Fake), \
             patch.object(m,'no_derivatives_or_open_orders'), \
             patch.object(m,'available', side_effect=lambda client, cc: Decimal('9') if cc=='USDT' else (Decimal('0') if not sent else Decimal('7.5'))), \
             patch.object(m,'scan',return_value={'watchlist':[candidate]}), \
             patch.object(m,'instrument',return_value={'instId':'TEST-USDT','state':'live','lotSz':'0.01','minSz':'0.1','tickSz':'0.0001'}), \
             patch.object(m,'fresh_ticker',return_value=(Decimal('1'),Decimal('0.999'))), \
             patch.object(m,'wait_filled',return_value=(Decimal('7.5'),Decimal('1'))), \
             patch.object(m,'verify_oco',return_value=True):
            outcome=m.execute(env,mode='live')
        self.assertIn('OCO CONFIRMED',outcome)
        self.assertEqual([x[0] for x in sent],['/api/v5/trade/order','/api/v5/trade/order-algo'])
        self.assertTrue(all(body['tdMode']=='cash' and body['instId']=='TEST-USDT' for _,body in sent))
        self.assertEqual(sent[1][1]['sz'],'7.5')

    def test_live_halts_if_oco_cannot_be_verified(self):
        import trading.okx_spot_live as m
        sent=[]
        class Fake:
            def __init__(self, env): pass
            def request(self, method, path, *, params=None, body=None):
                if method=='POST': sent.append(path)
                return []
        env={'OKX_API_KEY':'k','OKX_SECRET_KEY':'s','OKX_PASSPHRASE':'p',
             'OKX_EXECUTION_MODE':'live','OKX_ENABLE_REAL_TRADING':'YES',
             'OKX_SPOT_LIVE_ARM':'I_AUTHORIZE_REAL_CASH_SPOT_LOSS'}
        with patch.object(m,'OKXCash',Fake), \
             patch.object(m,'no_derivatives_or_open_orders'), \
             patch.object(m,'available',side_effect=lambda c,cc:Decimal('9') if cc=='USDT' else (Decimal('0') if not sent else Decimal('7.5'))), \
             patch.object(m,'scan',return_value={'watchlist':[{'symbol':'TEST-USDT','last_closed_bar_close':1}]}), \
             patch.object(m,'instrument',return_value={'instId':'TEST-USDT','state':'live','lotSz':'0.01','minSz':'0.1','tickSz':'0.0001'}), \
             patch.object(m,'fresh_ticker',return_value=(Decimal('1'),Decimal('0.999'))), \
             patch.object(m,'wait_filled',return_value=(Decimal('7.5'),Decimal('1'))), \
             patch.object(m,'verify_oco',side_effect=SpotHalt('OCO not confirmed')):
            with self.assertRaises(SpotHalt): m.execute(env,mode='live')
        self.assertEqual(sent,['/api/v5/trade/order','/api/v5/trade/order-algo'])
