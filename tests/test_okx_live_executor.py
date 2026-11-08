import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import patch
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from trading.okx_live_executor import (
    MODE_ARM, OKX, ExecutionBlocked, ReentryCooldownActive, check_mode, read_report, choose_signal,
    floor_step, contract_size, get_prices, client_order_id, daily_order_limit, execute, FULL_MARGIN_ARM, enforce_exit_cooldown, inspect_after_submit,
)


def make_signal():
    now=int(time.time()*1000)
    return {
      'symbol':'BTC-USDT-SWAP','quote_price':100.0,'signal':'LONG',
      'last_complete_15m_candle_ms':now-16*60*1000,
      'advanced_system_count':7, 'advanced_confirmations':2,
      'advanced_veto_reasons':[], 'derivatives_data_warnings':[],
      'execution':'DISABLED','order_count':0,
      'ordinal_buy_points':5, 'ordinal_sell_points':0,
      'agents':[{'agent':str(i),'evidence':{}} for i in range(5)] +
            [{'agent':'06_risk_marshal','evidence':{
                'indicative_stop_not_an_order':98, 'indicative_target_not_an_order':104}}]
    }


class TestLiveSafety(unittest.TestCase):
    def test_mode_opt_in_requires_arm_and_two_live_switches(self):
        with self.assertRaises(ExecutionBlocked):
            check_mode('live',{'OKX_ENABLE_REAL_TRADING':'YES'})
        with self.assertRaises(ExecutionBlocked):
            check_mode('live',{'OKX_EXECUTION_ARM':MODE_ARM['live']})
        with self.assertRaises(ExecutionBlocked):
            check_mode('live',{'OKX_EXECUTION_ARM':MODE_ARM['live'],
                              'OKX_ENABLE_REAL_TRADING':'YES'})
        env={'OKX_EXECUTION_ARM':MODE_ARM['live'],'OKX_ENABLE_REAL_TRADING':'YES',
             'OKX_API_KEY':'TEST','OKX_SECRET_KEY':'TEST','OKX_PASSPHRASE':'TEST'}
        check_mode('live',env)
        check_mode('dry_run',{})

    def test_hmac_matches_official_string(self):
        c=OKX({'OKX_SECRET_KEY':'abc','OKX_API_KEY':'x','OKX_PASSPHRASE':'p'})
        headers=c.make_auth('GET','/api/v5/account/balance?ccy=USDT','',at='2026-01-01T12:00:00.000Z')
        original='2026-01-01T12:00:00.000ZGET/api/v5/account/balance?ccy=USDT'
        import base64
        want=base64.b64encode(hmac.new(b'abc',original.encode(),hashlib.sha256).digest()).decode()
        self.assertEqual(headers['OK-ACCESS-SIGN'],want)

    def test_public_api_only_no_post(self):
        c=OKX({})
        with self.assertRaises(ExecutionBlocked):
            c.request('POST','/api/v5/trade/order',auth=False,body={})

    def test_reject_unrecognized_domains(self):
        with self.assertRaises(ExecutionBlocked):
            OKX({'OKX_API_DOMAIN':'http://evil.example'})

    def test_lot_round_down(self):
        self.assertEqual(floor_step('3.94','0.1'),Decimal('3.9'))
        self.assertEqual(floor_step('0.0019','0.001'),Decimal('0.001'))

    def test_small_equity_blocks_min_contract(self):
        i={'ctVal':'0.01','lotSz':'1','minSz':'1'}
        with self.assertRaises(ExecutionBlocked):
            contract_size(i,Decimal('100000'),Decimal('1'),Decimal('0.01'))

    def test_risk_size_never_above_equity_budget(self):
        i={'ctVal':'0.01','lotSz':'1','minSz':'1'}
        q=contract_size(i,Decimal('100'),Decimal('1000'),Decimal('0.02'))
        self.assertLessEqual(q*Decimal('0.01')*100*Decimal('0.02'),1000*Decimal('0.0025'))

    def test_full_margin_requires_its_own_arm(self):
        env={'OKX_EXECUTION_ARM':MODE_ARM['demo'],
             'OKX_API_KEY':'TEST','OKX_SECRET_KEY':'TEST','OKX_PASSPHRASE':'TEST',
             'OKX_CAPITAL_MODE':'full_margin'}
        with self.assertRaisesRegex(ExecutionBlocked, 'separately armed'):
            check_mode('demo', env)
        env['OKX_FULL_MARGIN_ARM']=FULL_MARGIN_ARM
        check_mode('demo', env)

    def test_full_margin_uses_up_to_available_margin_at_10x(self):
        inst={'ctVal':'1','lotSz':'1','minSz':'1'}
        quantity=contract_size(inst,Decimal('100'),Decimal('1000'),Decimal('0.005'),
                               capital_mode='full_margin',exchange_max='1000')
        self.assertEqual(quantity, Decimal('100'))  # $10k notional = 10x free USDT.
        limited=contract_size(inst,Decimal('100'),Decimal('1000'),Decimal('0.005'),
                              capital_mode='full_margin',exchange_max='32')
        self.assertEqual(limited,Decimal('32'))

    def test_full_margin_veto_if_stop_risk_too_high(self):
        inst={'ctVal':'1','lotSz':'1','minSz':'1'}
        with self.assertRaisesRegex(ExecutionBlocked, 'over 10% equity'):
            contract_size(inst,Decimal('100'),Decimal('1000'),Decimal('0.03'),
                          capital_mode='full_margin',exchange_max='1000')

    def test_full_margin_requires_fresh_exchange_limit(self):
        inst={'ctVal':'1','lotSz':'1','minSz':'1'}
        with self.assertRaises(ExecutionBlocked):
            contract_size(inst,Decimal('100'),Decimal('1000'),Decimal('0.005'),
                          capital_mode='full_margin')

    def test_reentry_blocks_until_10_minutes_after_full_close(self):
        class History:
            def __init__(self, rows):
                self.rows=rows
            def request(self, method, path, params=None):
                self_path='/api/v5/account/positions-history'
                if method != 'GET' or path != self_path or params != {'instType':'SWAP','limit':'100'}:
                    raise AssertionError('Unexpected API request')
                return self.rows
        clock=1_800_000_000_000
        full={'instType':'SWAP','type':'2','uTime':str(clock-9*60*1000)}
        with self.assertRaisesRegex(ExecutionBlocked, 'cooldown active'):
            enforce_exit_cooldown(History([full]), now_ms=clock)
        enforce_exit_cooldown(History([full]), now_ms=clock+60*1000)
        enforce_exit_cooldown(History([]), now_ms=clock)

    def test_liquidation_and_adl_closures_trigger_cooldown(self):
        clock=1_800_000_000_000
        class History:
            def __init__(self, kind):
                self.kind=kind
            def request(self, method, path, params=None):
                return [{'instType':'SWAP','type':self.kind,'uTime':str(clock-1000)}]
        for kind in ('3','6'):
            with self.assertRaises(ExecutionBlocked):
                enforce_exit_cooldown(History(kind),now_ms=clock)

    def test_partial_close_does_not_falsely_mark_full_exit(self):
        clock=1_800_000_000_000
        class History:
            def request(self, method, path, params=None):
                return [{'instType':'SWAP','type':'1','uTime':str(clock-1000)}]
        enforce_exit_cooldown(History(),now_ms=clock)

    def test_stale_or_unverifiable_history_fails_closed(self):
        clock=1_800_000_000_000
        class History:
            def __init__(self, rows):
                self.rows=rows
            def request(self, method, path, params=None):
                return self.rows
        with self.assertRaises(ExecutionBlocked):
            enforce_exit_cooldown(History([{'instType':'SWAP','type':'2','uTime':''}]),now_ms=clock)
        many=[{'instType':'SWAP','type':'1','uTime':str(clock-2000)} for _ in range(100)]
        with self.assertRaisesRegex(ExecutionBlocked, 'pagination'):
            enforce_exit_cooldown(History(many),now_ms=clock)

    def test_report_fresh_required(self):
        sig=make_signal()
        r={'mode':'SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY',
           'core_specialist_agents':6,'advanced_quant_systems':7,
           'utc_timestamp':'2024-01-01T00:00:00+00:00','errors':[], 'results':[sig]}
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.json'; p.write_text(json.dumps(r))
            with self.assertRaises(ExecutionBlocked):read_report(p)

    def test_choose_signal_requires_all_filters(self):
        sig=make_signal()
        report={'results':[sig]}
        self.assertEqual(choose_signal(report)['symbol'],'BTC-USDT-SWAP')
        sig['advanced_veto_reasons']=['jump']
        self.assertIsNone(choose_signal(report))

    def test_real_uni_nov8_signal_not_rejected_due_to_candle_open_age(self):
        # Actual no-consensus run: 23:45 candle opened, closed 00:00;
        # 00:13:41 UTC was 28m41s after OPEN but only 13m41s after CLOSE.
        signal=make_signal()
        signal['symbol']='UNI-USDT-SWAP'
        signal['quote_price']=7.218
        signal['agents'][-1]['evidence']={
            'indicative_stop_not_an_order':7.092,
            'indicative_target_not_an_order':7.47}
        signal['last_complete_15m_candle_ms']=1794095100000
        now=1794096821975
        self.assertIsNotNone(choose_signal({'results':[signal]},now_ms=now))

    def test_reject_candle_that_has_not_closed(self):
        signal=make_signal()
        now=1_800_000_000_000
        signal['last_complete_15m_candle_ms']=now-10*60*1000
        self.assertIsNone(choose_signal({'results':[signal]},now_ms=now))

    def test_reject_candle_older_than_one_full_period_after_close(self):
        signal=make_signal()
        now=1_800_000_000_000
        signal['last_complete_15m_candle_ms']=now-31*60*1000
        self.assertIsNone(choose_signal({'results':[signal]},now_ms=now))

    def test_15m_candle_just_closed_is_eligible(self):
        signal=make_signal()
        now=1_800_000_000_000
        signal['last_complete_15m_candle_ms']=now-15*60*1000
        self.assertIsNotNone(choose_signal({'results':[signal]},now_ms=now))

    def test_price_rounding_and_stop(self):
        sig=make_signal()
        price,stop,target,delta=get_prices(sig,{'last':'100','askPx':'100.1','bidPx':'99.9'},
                                          {'tickSz':'0.01'})
        self.assertEqual(stop,Decimal('98'))
        self.assertEqual(target,Decimal('104'))
        self.assertGreater(delta,0)

    def test_id_deterministic_and_bounded(self):
        a=make_signal()
        self.assertEqual(client_order_id(a),client_order_id(a))
        self.assertLessEqual(len(client_order_id(a)),32)

    def test_no_fixed_24h_bot_order_count_limit_but_duplicate_guard_remains(self):
        import inspect
        code=inspect.getsource(execute)
        self.assertNotIn('MAX_DAILY_BOT_ORDERS',code)
        self.assertEqual(code.count('daily_order_limit(client,candidate_id=clordid)'),2)
        now=int(time.time()*1000)
        class History:
            def request(self,method,path,params=None):
                return [{'ordId':str(i),'cTime':str(now),'clOrdId':'Q37DUP'+str(i)}
                        for i in range(15)]
        self.assertEqual(daily_order_limit(History()),15)
        with self.assertRaisesRegex(ExecutionBlocked, 'Same client order'):
            daily_order_limit(History(),candidate_id='Q37DUP9')

    def test_uncertain_entry_status_attempts_reduce_only_close(self):
        sig=make_signal()
        class Uncertain:
            def __init__(self):self.closes=[]
            def request(self,method,path,params=None,body=None):
                if path=='/api/v5/trade/order' and method=='GET':
                    raise ExecutionBlocked('Transport unavailable')
                if path=='/api/v5/account/positions':
                    return [{'pos':'2'}]
                if path=='/api/v5/trade/order' and method=='POST':
                    self.closes.append(body)
                    return [{'sCode':'0'}]
                raise AssertionError((method,path))
        c=Uncertain()
        with patch('trading.okx_live_executor.time.sleep',return_value=None):
            with self.assertRaisesRegex(ExecutionBlocked, 'URGENT: Entry order status'):
                inspect_after_submit(c,sig,'Q37TEST')
        self.assertEqual(len(c.closes),1)
        self.assertTrue(c.closes[0]['reduceOnly'])
        self.assertEqual(c.closes[0]['side'],'sell')
        self.assertEqual(c.closes[0]['sz'],'2')

    def test_missing_order_confirmation_attempts_emergency_close(self):
        sig=make_signal()
        class Missing:
            def __init__(self):self.closes=[]
            def request(self,method,path,params=None,body=None):
                if path=='/api/v5/trade/order' and method=='GET':
                    return []
                if path=='/api/v5/account/positions':
                    return [{'pos':'1'}]
                if path=='/api/v5/trade/order' and method=='POST':
                    self.closes.append(body)
                    return [{'sCode':'0'}]
                raise AssertionError((method,path))
        c=Missing()
        with patch('trading.okx_live_executor.time.sleep',return_value=None):
            with self.assertRaisesRegex(ExecutionBlocked,'URGENT: Entry order confirmation'):
                inspect_after_submit(c,sig,'Q37TEST')
        self.assertEqual(len(c.closes),1)
        self.assertTrue(c.closes[0]['reduceOnly'])

    def test_unverifiable_stop_protection_attempts_emergency_close(self):
        sig=make_signal()
        class Unreadable:
            def __init__(self):self.closes=[]
            def request(self,method,path,params=None,body=None):
                if path=='/api/v5/trade/order' and method=='GET':
                    return [{'state':'filled'}]
                if path=='/api/v5/trade/orders-algo-pending':
                    raise ExecutionBlocked('Protection unavailable')
                if path=='/api/v5/account/positions':
                    return [{'pos':'3'}]
                if path=='/api/v5/trade/order' and method=='POST':
                    self.closes.append(body)
                    return [{'sCode':'0'}]
                raise AssertionError((method,path))
        c=Unreadable()
        with patch('trading.okx_live_executor.time.sleep',return_value=None):
            with self.assertRaisesRegex(ExecutionBlocked,'URGENT: Protective order status'):
                inspect_after_submit(c,sig,'Q37TEST')
        self.assertEqual(len(c.closes),1)
        self.assertEqual(c.closes[0]['sz'],'3')
        self.assertTrue(c.closes[0]['reduceOnly'])

    def test_uncertain_entry_and_failed_close_requires_manual_inspection(self):
        sig=make_signal()
        class Bad:
            def request(self,method,path,params=None,body=None):
                raise ExecutionBlocked('Exchange unreachable')
        with patch('trading.okx_live_executor.time.sleep',return_value=None):
            with self.assertRaisesRegex(ExecutionBlocked,'emergency close could not be verified'):
                inspect_after_submit(Bad(),sig,'Q37TEST')

    def test_verified_protection_never_sends_close(self):
        sig=make_signal()
        class Protected:
            def __init__(self):self.posts=0
            def request(self,method,path,params=None,body=None):
                if method=='GET' and path=='/api/v5/trade/order':
                    return [{'state':'filled'}]
                if method=='GET' and path=='/api/v5/trade/orders-algo-pending':
                    return [{'instId':'BTC-USDT-SWAP','slTriggerPx':'98','tpTriggerPx':'104'}] if params['ordType']=='oco' else []
                if method=='POST':self.posts+=1
                raise AssertionError((method,path))
        c=Protected()
        with patch('trading.okx_live_executor.time.sleep',return_value=None):
            self.assertEqual(inspect_after_submit(c,sig,'Q37TEST'),'FILLED_PROTECTED')
        self.assertEqual(c.posts,0)

    def test_dry_run_performs_zero_http_calls(self):
        sig=make_signal()
        report={'results':[sig]}
        class Never:
            def request(self,*args,**kwargs):
                raise AssertionError('Dry run called API unexpectedly')
        result=execute(report,Never(),'dry_run',{})
        self.assertEqual(result,'DRY_RUN_SIGNAL_ONLY')

    def test_daily_order_count_from_exchange_history(self):
        ms=int(time.time()*1000)
        class Fake:
            def request(self,method,path,params=None):
                return [{'ordId':'1','cTime':str(ms),'clOrdId':'Q37ABC'},
                        {'ordId':'2','cTime':str(ms),'clOrdId':'manual'}]
        self.assertEqual(daily_order_limit(Fake()),1)
        with self.assertRaises(ExecutionBlocked):
            daily_order_limit(Fake(),candidate_id='Q37ABC')

if __name__=='__main__': unittest.main()

class AutoReentrySizingTests(unittest.TestCase):
    def test_unarmed_full_margin_still_rejected(self):
        report={"results":[make_signal()]}
        env={"OKX_EXECUTION_MODE":"live","OKX_EXECUTION_ARM":MODE_ARM["live"],
             "OKX_ENABLE_REAL_TRADING":"YES","OKX_API_KEY":"fake",
             "OKX_SECRET_KEY":"fake","OKX_PASSPHRASE":"fake",
             "OKX_CAPITAL_MODE":"full_margin",
             "OKX_AUTOREENTRY_ENABLED":"YES"}
        with self.assertRaisesRegex(ExecutionBlocked,"separately armed"):
            execute(report,object(),"live",env)

    def test_armed_auto_reentry_full_margin_has_no_daily_count_cap(self):
        from datetime import datetime, timezone
        report={"results":[make_signal()],"utc_timestamp":datetime.now(timezone.utc).isoformat()}
        env={"OKX_EXECUTION_MODE":"live","OKX_EXECUTION_ARM":MODE_ARM["live"],
             "OKX_ENABLE_REAL_TRADING":"YES","OKX_API_KEY":"fake",
             "OKX_SECRET_KEY":"fake","OKX_PASSPHRASE":"fake",
             "OKX_CAPITAL_MODE":"full_margin",
             "OKX_FULL_MARGIN_ARM":FULL_MARGIN_ARM,
             "OKX_AUTOREENTRY_ENABLED":"YES"}
        class FakeExchange:
            def __init__(self):
                self.paths=[]
            def request(self, method, path, params=None, body=None):
                self.paths.append((method,path))
                if path=="/api/v5/account/max-size":
                    return [{"maxBuy":"200","maxSell":"200"}]
                if path in ("/api/v5/account/positions","/api/v5/trade/orders-pending"):
                    return []
                if path=="/api/v5/account/set-leverage":
                    return [{"lever":"10"}]
                raise AssertionError("Unexpected exchange request: "+path)
        client=FakeExchange()
        with (patch("trading.okx_live_executor.market_preflight",
                    return_value=({"last":"100","bidPx":"99.9","askPx":"100.1"},
                                  {"tickSz":"0.1","lotSz":"1","ctVal":"1"})),
              patch("trading.okx_live_executor.account_preflight",
                    return_value=Decimal("1000")),
              patch("trading.okx_live_executor.enforce_exit_cooldown") as cooldown,
              patch("trading.okx_live_executor.daily_order_limit",
                    return_value=999) as history,
              patch("trading.okx_live_executor.get_prices",
                    return_value=(Decimal("100"),Decimal("99"),Decimal("103"),Decimal("0.01"))),
              patch("trading.okx_live_executor.contract_size",
                    return_value=Decimal("100")) as sizing):
            self.assertEqual(execute(report,client,"live",env,allow_post=False),
                             "PREPARED_BUT_NOT_SENT")
        self.assertEqual(history.call_count,2)
        self.assertEqual(cooldown.call_count,2)
        self.assertEqual(sizing.call_args.kwargs["capital_mode"],"full_margin")
        self.assertFalse(any(p=="/api/v5/trade/order" for _,p in client.paths))

class CooldownRaceSafetyTests(unittest.TestCase):
    """A late exchange-history update must pause, never kill the chain or trade."""

    @staticmethod
    def env(autoreentry="YES"):
        return {"OKX_EXECUTION_MODE":"live",
                "OKX_EXECUTION_ARM":MODE_ARM["live"],
                "OKX_ENABLE_REAL_TRADING":"YES",
                "OKX_API_KEY":"test","OKX_SECRET_KEY":"test",
                "OKX_PASSPHRASE":"test","OKX_CAPITAL_MODE":"guarded",
                "OKX_AUTOREENTRY_ENABLED":autoreentry}

    def test_cooldown_exception_is_distinct_from_other_exchange_failures(self):
        self.assertTrue(issubclass(ReentryCooldownActive,ExecutionBlocked))
        clock=1_800_000_000_000
        class History:
            def request(self,method,path,params=None):
                return [{"instType":"SWAP","type":"2","uTime":str(clock-30_000)}]
        with self.assertRaises(ReentryCooldownActive):
            enforce_exit_cooldown(History(),now_ms=clock)

    def test_newly_reported_cooldown_before_private_order_is_nonfatal_no_order(self):
        from datetime import datetime, timezone
        report={"results":[make_signal()],
                "utc_timestamp":datetime.now(timezone.utc).isoformat()}
        with (patch("trading.okx_live_executor.market_preflight",
                    return_value=({"last":"100"},{ "tickSz":"0.1"})),
              patch("trading.okx_live_executor.account_preflight",
                    return_value=Decimal("1000")),
              patch("trading.okx_live_executor.enforce_exit_cooldown",
                    side_effect=ReentryCooldownActive("wait")) as cooldown):
            self.assertEqual(execute(report,object(),"live",self.env()),
                             "REENTRY_COOLDOWN_NO_ORDER")
            cooldown.assert_called_once()

    def test_unarmed_mode_still_blocks_same_cooldown(self):
        report={"results":[make_signal()]}
        with (patch("trading.okx_live_executor.market_preflight",
                    return_value=({},{})),
              patch("trading.okx_live_executor.account_preflight",
                    return_value=Decimal("1000")),
              patch("trading.okx_live_executor.enforce_exit_cooldown",
                    side_effect=ReentryCooldownActive("wait"))):
            with self.assertRaises(ReentryCooldownActive):
                execute(report,object(),"live",self.env("NO"))

    def test_invalid_history_still_aborts_recurring_executor(self):
        report={"results":[make_signal()]}
        with (patch("trading.okx_live_executor.market_preflight",
                    return_value=({},{})),
              patch("trading.okx_live_executor.account_preflight",
                    return_value=Decimal("1000")),
              patch("trading.okx_live_executor.enforce_exit_cooldown",
                    side_effect=ExecutionBlocked("history pagination unverified"))):
            with self.assertRaisesRegex(ExecutionBlocked,"pagination"):
                execute(report,object(),"live",self.env())

    def test_cooldown_detected_on_last_exchange_check_prevents_order(self):
        from datetime import datetime, timezone
        report={"results":[make_signal()],
                "utc_timestamp":datetime.now(timezone.utc).isoformat()}
        class Client:
            def __init__(self):self.calls=[]
            def request(self,method,path,params=None,body=None):
                self.calls.append((method,path))
                if path=="/api/v5/account/set-leverage":return [{"lever":"10"}]
                if path=="/api/v5/account/max-size":return [{"maxBuy":"100"}]
                if path in ("/api/v5/account/positions","/api/v5/trade/orders-pending"):
                    return []
                raise AssertionError("unexpected API endpoint: "+path)
        client=Client()
        with (patch("trading.okx_live_executor.market_preflight",
                    return_value=({"last":"100"},{ "tickSz":"0.1"})),
              patch("trading.okx_live_executor.account_preflight",
                    return_value=Decimal("1000")),
              patch("trading.okx_live_executor.daily_order_limit",
                    return_value=0),
              patch("trading.okx_live_executor.get_prices",
                    return_value=(Decimal("100"),Decimal("99"),Decimal("102"),Decimal("0.01"))),
              patch("trading.okx_live_executor.contract_size",
                    return_value=Decimal("10")),
              patch("trading.okx_live_executor.enforce_exit_cooldown",
                    side_effect=[True,ReentryCooldownActive("late close")]) as cooldown):
            self.assertEqual(execute(report,client,"live",self.env()),
                             "REENTRY_COOLDOWN_NO_ORDER")
        self.assertEqual(cooldown.call_count,2)
        self.assertNotIn(("POST","/api/v5/trade/order"),client.calls)
