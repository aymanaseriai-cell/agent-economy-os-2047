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

    def test_full_margin_uses_up_to_available_margin_at_20x(self):
        inst={'ctVal':'1','lotSz':'1','minSz':'1'}
        quantity=contract_size(inst,Decimal('100'),Decimal('1000'),Decimal('0.005'),
                               capital_mode='full_margin',exchange_max='1000')
        self.assertEqual(quantity, Decimal('200'))  # $20k notional = 20x free USDT.
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

    def test_reentry_blocks_until_30_seconds_after_full_close(self):
        class History:
            def __init__(self, rows):
                self.rows=rows
            def request(self, method, path, params=None):
                self_path='/api/v5/account/positions-history'
                if method != 'GET' or path != self_path or params != {'instType':'SWAP','limit':'100'}:
                    raise AssertionError('Unexpected API request')
                return self.rows
        clock=1_800_000_000_000
        full={'instType':'SWAP','type':'2','uTime':str(clock-29*1000)}
        with self.assertRaisesRegex(ExecutionBlocked, 'cooldown active'):
            enforce_exit_cooldown(History([full]), now_ms=clock)
        enforce_exit_cooldown(History([full]), now_ms=clock+1000)
        enforce_exit_cooldown(History([]), now_ms=clock)
        recent={'instType':'SWAP','type':'2','uTime':str(clock-30*1000)}
        enforce_exit_cooldown(History([recent]),now_ms=clock)
        old={'instType':'SWAP','type':'2','uTime':str(clock-9*60*1000)}
        enforce_exit_cooldown(History([old]),now_ms=clock)

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
                return [{"instType":"SWAP","type":"2","uTime":str(clock-29_000)}]
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

class FullMarginRiskVetoRecoveryTests(unittest.TestCase):
    """Same excessive-stop case seen in live Actions must skip, never trade."""

    @staticmethod
    def fixture_env(autorreentry="YES"):
        return {"OKX_EXECUTION_MODE":"live",
                "OKX_EXECUTION_ARM":MODE_ARM["live"],
                "OKX_ENABLE_REAL_TRADING":"YES",
                "OKX_API_KEY":"test","OKX_SECRET_KEY":"test",
                "OKX_PASSPHRASE":"test",
                "OKX_CAPITAL_MODE":"Full_margin",
                "OKX_FULL_MARGIN_ARM":FULL_MARGIN_ARM,
                "OKX_AUTOREENTRY_ENABLED":autorreentry}

    def test_repeated_full_margin_risk_reject_skips_without_trade(self):
        from trading.okx_live_executor import OpportunityRiskRejected
        from datetime import datetime, timezone
        report={"results":[make_signal()],
                "utc_timestamp":datetime.now(timezone.utc).isoformat()}
        class FakeExchange:
            def __init__(self): self.calls=[]
            def request(self,method,path,params=None,body=None):
                self.calls.append((method,path))
                if path=="/api/v5/account/set-leverage":return [{"lever":"10"}]
                if path=="/api/v5/account/max-size":
                    return [{"maxBuy":"1000","maxSell":"1000"}]
                raise AssertionError("Unexpected OKX endpoint "+path)
        client=FakeExchange()
        with (patch("trading.okx_live_executor.market_preflight",
                    return_value=({"last":"100"},{"ctVal":"1","lotSz":"1","minSz":"1"})),
              patch("trading.okx_live_executor.account_preflight",
                    return_value=Decimal("1000")),
              patch("trading.okx_live_executor.enforce_exit_cooldown"),
              patch("trading.okx_live_executor.daily_order_limit",
                    return_value=42),
              patch("trading.okx_live_executor.get_prices",
                    return_value=(Decimal("100"),Decimal("98"),Decimal("103"),Decimal("0.02")))):
            # Full margin 10x $1000, $100 price: 100 contracts;
            # stop 2% -> $200 planned loss, so $100 maximum rejects.
            self.assertEqual(execute(report,client,"live",self.fixture_env()),
                             "RISK_REJECTED_NO_ORDER")
            with self.assertRaises(OpportunityRiskRejected):
                execute(report,client,"live",self.fixture_env("NO"))
        self.assertNotIn(("POST","/api/v5/trade/order"),client.calls)
        self.assertFalse(any("/positions" in path for _,path in client.calls))

    def test_no_relaxation_of_full_margin_10pct_cap(self):
        from trading.okx_live_executor import (
            OpportunityRiskRejected, contract_size, MAX_FULL_MARGIN_PLANNED_STOP_RISK
        )
        self.assertEqual(MAX_FULL_MARGIN_PLANNED_STOP_RISK,Decimal("0.10"))
        with self.assertRaises(OpportunityRiskRejected):
            contract_size({"ctVal":"1","lotSz":"1","minSz":"1"},
                          Decimal("100"),Decimal("1000"),Decimal("0.02"),
                          capital_mode="full_margin",exchange_max="1000")



class ComprehensivePreOrderVetoTests(unittest.TestCase):
    """Regression matrix for safe skip versus fatal exchange uncertainty."""

    @staticmethod
    def env(armed="YES"):
        return {"OKX_EXECUTION_MODE":"live",
                "OKX_EXECUTION_ARM":MODE_ARM["live"],
                "OKX_ENABLE_REAL_TRADING":"YES",
                "OKX_API_KEY":"test", "OKX_SECRET_KEY":"test",
                "OKX_PASSPHRASE":"test","OKX_CAPITAL_MODE":"guarded",
                "OKX_AUTOREENTRY_ENABLED":armed}

    def test_local_stop_and_target_rejection_matrix_has_no_order(self):
        from trading.okx_live_executor import CandidateRejected, get_prices
        # Both LONG and SHORT; reject stops too near, too far, or targets
        # crossing the live market. These are candidate failures, not outages.
        ticker={"last":"100","askPx":"100.1","bidPx":"99.9"}
        inst={"tickSz":"0.1"}
        for direction,stop,target in [
            ("LONG","100.09","103"), ("LONG","96","103"),
            ("LONG","99","99"), ("SHORT","99.95","97"),
            ("SHORT","104","97"), ("SHORT","101","101")
        ]:
            signal={"signal":direction,"agents":[{"evidence":{
                "indicative_stop_not_an_order":stop,
                "indicative_target_not_an_order":target}}]}
            with self.subTest(direction=direction,stop=stop,target=target):
                with self.assertRaises(CandidateRejected):
                    get_prices(signal,ticker,inst)

    def test_executor_skips_precisely_classified_preorder_errors(self):
        from trading.okx_live_executor import CandidateRejected
        report={"results":[make_signal()]}
        # Exercise preflight (market) and late local stop checks independently.
        for failure_phase in ("market","prices"):
            with self.subTest(failure_phase=failure_phase):
                def market(*args,**kwargs):
                    if failure_phase=="market":
                        raise CandidateRejected("spread too wide")
                    return ({},{})
                with (patch("trading.okx_live_executor.market_preflight",
                            side_effect=market),
                      patch("trading.okx_live_executor.account_preflight",
                            return_value=Decimal("100")),
                      patch("trading.okx_live_executor.enforce_exit_cooldown"),
                      patch("trading.okx_live_executor.daily_order_limit",
                            return_value=0),
                      patch("trading.okx_live_executor.get_prices",
                            side_effect=CandidateRejected("invalid stop"))):
                    self.assertEqual(execute(report,object(),"live",self.env()),
                                     "CANDIDATE_REJECTED_NO_ORDER")
                    with self.assertRaises(CandidateRejected):
                        execute(report,object(),"live",self.env("NO"))

    def test_exact_duplicate_is_safe_candidate_skip_not_a_new_order(self):
        from trading.okx_live_executor import DuplicateCandidateRejected
        report={"results":[make_signal()]}
        with (patch("trading.okx_live_executor.market_preflight",return_value=({},{})),
              patch("trading.okx_live_executor.account_preflight",
                    return_value=Decimal("100")),
              patch("trading.okx_live_executor.enforce_exit_cooldown"),
              patch("trading.okx_live_executor.daily_order_limit",
                    side_effect=DuplicateCandidateRejected("replay"))):
            self.assertEqual(execute(report,object(),"live",self.env()),
                             "CANDIDATE_REJECTED_NO_ORDER")

    def test_any_exchange_error_still_fails_closed(self):
        report={"results":[make_signal()]}
        with patch("trading.okx_live_executor.market_preflight",
                   side_effect=ExecutionBlocked("network error")):
            with self.assertRaisesRegex(ExecutionBlocked,"network"):
                execute(report,object(),"live",self.env())

    def test_freshness_expired_only_is_rescannable(self):
        from trading.nvidia_execution_gate import GateRejected
        from datetime import datetime, timezone
        report={"results":[make_signal()],
                "utc_timestamp":datetime.now(timezone.utc).isoformat()}
        class NoTrade:
            def __init__(self):self.calls=[]
            def request(self,method,path,params=None,body=None):
                self.calls.append((method,path))
                if path=="/api/v5/account/set-leverage":return [{"lever":"10"}]
                if path=="/api/v5/account/max-size":return [{"maxBuy":"500"}]
                if path in ("/api/v5/account/positions","/api/v5/trade/orders-pending"):
                    return []
                raise AssertionError("Unexpected request "+path)
        client=NoTrade()
        with (patch("trading.okx_live_executor.market_preflight",
                    return_value=({},{})),
              patch("trading.okx_live_executor.account_preflight",
                    return_value=Decimal("1000")),
              patch("trading.okx_live_executor.enforce_exit_cooldown"),
              patch("trading.okx_live_executor.daily_order_limit",return_value=0),
              patch("trading.okx_live_executor.get_prices",
                    return_value=(Decimal("100"),Decimal("99"),Decimal("103"),Decimal("0.01"))),
              patch("trading.okx_live_executor.contract_size",return_value=Decimal("10")),
              patch("trading.okx_live_executor._fresh_report",
                    side_effect=GateRejected("Market report expired during NVIDIA review"))):
            self.assertEqual(execute(report,client,"live",self.env()),
                             "STALE_SIGNAL_NO_ORDER")
        self.assertNotIn(("POST","/api/v5/trade/order"),client.calls)

    def test_malformed_report_does_not_become_safe_skip(self):
        from trading.nvidia_execution_gate import GateRejected
        from datetime import datetime, timezone
        report={"results":[make_signal()],
                "utc_timestamp":datetime.now(timezone.utc).isoformat()}
        class Preflight:
            def request(self,method,path,params=None,body=None):
                if path=="/api/v5/account/set-leverage":return [{"lever":"10"}]
                if path=="/api/v5/account/max-size":return [{"maxBuy":"500"}]
                if path in ("/api/v5/account/positions","/api/v5/trade/orders-pending"):
                    return []
                raise AssertionError(path)
        with (patch("trading.okx_live_executor.market_preflight",return_value=({},{})),
              patch("trading.okx_live_executor.account_preflight",
                    return_value=Decimal("1000")),
              patch("trading.okx_live_executor.enforce_exit_cooldown"),
              patch("trading.okx_live_executor.daily_order_limit",return_value=0),
              patch("trading.okx_live_executor.get_prices",
                    return_value=(Decimal("100"),Decimal("99"),Decimal("103"),Decimal("0.01"))),
              patch("trading.okx_live_executor.contract_size",return_value=Decimal("10")),
              patch("trading.okx_live_executor._fresh_report",
                    side_effect=GateRejected("Market report timestamp unavailable"))):
            with self.assertRaisesRegex(ExecutionBlocked,"timestamp unavailable"):
                execute(report,Preflight(),"live",self.env())


class OmegaExecutionSelectionTests(unittest.TestCase):
    def test_vetoed_or_nonpositive_rank_cannot_trade(self):
        s=make_signal()
        s.update(omega_system_count=10, omega_rank_score=0.1, omega_veto_reasons=['adversary'])
        self.assertIsNone(choose_signal({'results':[s]}))
        s['omega_veto_reasons']=[]
        s['omega_rank_score']=0
        self.assertIsNone(choose_signal({'results':[s]}))

    def test_omega_report_required_under_explicit_guard(self):
        with self.assertRaisesRegex(ExecutionBlocked,'Missing TITAN Omega'):
            execute({'results':[make_signal()]},object(),'dry_run',{'OKX_REQUIRE_OMEGA':'YES'})


class AdaptiveGuardedSizingTests(unittest.TestCase):
    def test_adaptive_mode_accepted_without_full_margin_arm(self):
        env={'OKX_EXECUTION_ARM':MODE_ARM['demo'],
             'OKX_API_KEY':'TEST','OKX_SECRET_KEY':'TEST','OKX_PASSPHRASE':'TEST',
             'OKX_CAPITAL_MODE':'adaptive_guarded'}
        check_mode('demo', env)

    def test_adaptive_scales_down_20x_full_margin_risk_veto(self):
        # $1000 free equity, $100 per contract, 2% stop.
        # Full margin fails the existing 10%-equity risk invariant.
        from trading.okx_live_executor import OpportunityRiskRejected
        i={'ctVal':'1','lotSz':'1','minSz':'1'}
        with self.assertRaises(OpportunityRiskRejected):
            contract_size(i,Decimal('100'),Decimal('1000'),Decimal('0.02'),
                          capital_mode='full_margin',exchange_max='1000')
        q=contract_size(i,Decimal('100'),Decimal('1000'),Decimal('0.02'),
                        capital_mode='adaptive_guarded',exchange_max='1000')
        self.assertEqual(q,Decimal('10'))
        # 10 contracts * $100 * 2% stop = $20 = 2% equity.
        self.assertLessEqual(q*Decimal('100')*Decimal('0.02'),Decimal('20'))
        self.assertLessEqual(q*Decimal('100')/Decimal('20'),Decimal('200'))

    def test_adaptive_respects_orderbook_exchange_max_and_step(self):
        i={'ctVal':'1','lotSz':'0.25','minSz':'0.25'}
        q=contract_size(i,Decimal('100'),Decimal('1000'),Decimal('0.01'),
                        capital_mode='adaptive_guarded',exchange_max='3.1')
        self.assertEqual(q,Decimal('3.00'))

    def test_adaptive_does_not_oversize_very_small_account(self):
        i={'ctVal':'1','lotSz':'1','minSz':'1'}
        with self.assertRaisesRegex(ExecutionBlocked, 'minimum'):
            contract_size(i,Decimal('100'),Decimal('5'),Decimal('0.02'),
                          capital_mode='adaptive_guarded',exchange_max='1000')

    def test_adaptive_missing_exchange_max_fails_closed(self):
        i={'ctVal':'1','lotSz':'1','minSz':'1'}
        with self.assertRaisesRegex(ExecutionBlocked, 'fresh OKX max-size'):
            contract_size(i,Decimal('100'),Decimal('1000'),Decimal('0.01'),
                          capital_mode='adaptive_guarded')

    def test_adaptive_20x_does_not_use_all_margin(self):
        from trading.okx_live_executor import (
            ADAPTIVE_EQUITY_RISK_FRACTION, ADAPTIVE_MARGIN_CAP_FRACTION,
            ADAPTIVE_NOTIONAL_CAP_FRACTION, LEVERAGE
        )
        self.assertEqual(LEVERAGE,20)
        self.assertLessEqual(ADAPTIVE_EQUITY_RISK_FRACTION,Decimal('0.02'))
        self.assertLessEqual(ADAPTIVE_MARGIN_CAP_FRACTION,Decimal('0.20'))
        self.assertLessEqual(ADAPTIVE_NOTIONAL_CAP_FRACTION,Decimal('4.0'))


class OptionalMultiPositionEntryTests(unittest.TestCase):
    def test_up_to_ten_and_separate_arm_in_real_mode(self):
        env={'OKX_EXECUTION_ARM':MODE_ARM['live'],
             'OKX_API_KEY':'TEST','OKX_SECRET_KEY':'TEST','OKX_PASSPHRASE':'TEST',
             'OKX_ENABLE_REAL_TRADING':'YES','OKX_EXECUTION_MODE':'live',
             'OKX_STOP_CONTINUOUS':'NO',
             'OKX_CAPITAL_MODE':'adaptive_guarded',
             'OKX_MAX_ACTIVE_POSITIONS':'2','OKX_PORTFOLIO_ARM':'YES'}
        check_mode('live',env)
        with self.assertRaisesRegex(ExecutionBlocked,'separate portfolio arm'):
            check_mode('live',{**env,'OKX_PORTFOLIO_ARM':'NO'})
        for capacity in ('1','2','5','9','10'):
            check_mode('live',{**env,'OKX_MAX_ACTIVE_POSITIONS':capacity})
        for capacity in ('0','11','x','-2','1.5'):
            with self.assertRaisesRegex(ExecutionBlocked,'Maximum open positions'):
                check_mode('live',{**env,'OKX_MAX_ACTIVE_POSITIONS':capacity})
        with self.assertRaisesRegex(ExecutionBlocked,'adaptive_guarded'):
            check_mode('live',{**env,'OKX_CAPITAL_MODE':'guarded'})

    def test_choose_excludes_already_held_market(self):
        sig=make_signal()
        copy=dict(sig)
        copy['symbol']='ETH-USDT-SWAP'
        report={'results':[sig,copy]}
        self.assertEqual(choose_signal(report,exclude_symbols={'BTC-USDT-SWAP'})['symbol'],
                         'ETH-USDT-SWAP')
        self.assertIsNone(choose_signal(report,exclude_symbols={'BTC-USDT-SWAP',
                                                                'ETH-USDT-SWAP'}))

class TenPositionAccountCapTests(unittest.TestCase):
    def test_limit_one_is_valid_without_portfolio_arm(self):
        env={'OKX_EXECUTION_ARM':MODE_ARM['live'],
             'OKX_API_KEY':'T','OKX_SECRET_KEY':'T','OKX_PASSPHRASE':'T',
             'OKX_ENABLE_REAL_TRADING':'YES','OKX_STOP_CONTINUOUS':'NO',
             'OKX_CAPITAL_MODE':'guarded',
             'OKX_MAX_ACTIVE_POSITIONS':'1','OKX_PORTFOLIO_ARM':'NO'}
        check_mode('live',env)

    def test_all_higher_capacities_need_adaptive_and_explicit_arm(self):
        env={'OKX_EXECUTION_ARM':MODE_ARM['live'],
             'OKX_API_KEY':'T','OKX_SECRET_KEY':'T','OKX_PASSPHRASE':'T',
             'OKX_ENABLE_REAL_TRADING':'YES','OKX_STOP_CONTINUOUS':'NO',
             'OKX_CAPITAL_MODE':'adaptive_guarded',
             'OKX_MAX_ACTIVE_POSITIONS':'10','OKX_PORTFOLIO_ARM':'YES'}
        check_mode('live',env)
        with self.assertRaisesRegex(ExecutionBlocked,'separate portfolio arm'):
            check_mode('live',{**env,'OKX_PORTFOLIO_ARM':'NO'})
        with self.assertRaisesRegex(ExecutionBlocked,'adaptive_guarded'):
            check_mode('live',{**env,'OKX_CAPITAL_MODE':'full_margin',
                               'OKX_FULL_MARGIN_ARM':FULL_MARGIN_ARM})

class ExchangeAdvertisedTwentyXGateTests(unittest.TestCase):
    def test_market_preflight_rejects_leverage_under_20_without_order(self):
        from trading.okx_live_executor import market_preflight, CandidateRejected
        from unittest.mock import patch
        now=int(time.time()*1000)
        class PublicOnly:
            def __init__(self, lever): self.lever=lever; self.calls=[]
            def request(self,method,path,params=None,auth=True):
                self.calls.append((method,path))
                if path=='/api/v5/market/ticker':
                    return [{'instId':'BTC-USDT-SWAP','last':'100',
                             'bidPx':'99.99','askPx':'100.01','volCcy24h':'500000',
                             'ts':str(now)}]
                if path=='/api/v5/public/instruments':
                    return [{'instId':'BTC-USDT-SWAP','state':'live',
                             'ctType':'linear','settleCcy':'USDT','ctValCcy':'BTC',
                             'instCategory':'1','ruleType':'normal','lever':self.lever}]
                raise AssertionError('Should be public GET only')
        sig={'symbol':'BTC-USDT-SWAP','quote_price':100}
        for lever in ('10','19.99','',None,'NaN'):
            client=PublicOnly(lever)
            with self.assertRaises(CandidateRejected):
                market_preflight(client,sig)
            self.assertTrue(all(m=='GET' for m,_ in client.calls))
        allowed=PublicOnly('20')
        with patch('trading.okx_live_executor.time.time',return_value=now/1000):
            _,inst=market_preflight(allowed,sig)
        self.assertEqual(inst['lever'],'20')

    def test_live_rejects_illiquid_even_when_twenty_x_supported(self):
        from trading.okx_live_executor import market_preflight, CandidateRejected
        now=int(time.time()*1000)
        class Tiny:
            def request(self,method,path,params=None,auth=True):
                if path=='/api/v5/market/ticker':
                    return [{'instId':'BTC-USDT-SWAP','last':'100',
                             'bidPx':'99.99','askPx':'100.01',
                             'volCcy24h':'1000','ts':str(now)}]
                if path=='/api/v5/public/instruments':
                    return [{'instId':'BTC-USDT-SWAP','state':'live',
                             'ctType':'linear','settleCcy':'USDT',
                             'ctValCcy':'BTC','instCategory':'1','lever':'20'}]
                raise AssertionError(path)
        with self.assertRaisesRegex(CandidateRejected,'turnover'):
            market_preflight(Tiny(),{'symbol':'BTC-USDT-SWAP','quote_price':100})

class CryptocurrencyOnlyTwentyXGateTests(unittest.TestCase):
    def test_stock_perpetual_cannot_trade_even_with_20x(self):
        from trading.okx_live_executor import market_preflight, CandidateRejected
        now=int(time.time()*1000)
        class Equity:
            def request(self,method,path,params=None,auth=True):
                if method!='GET':
                    raise AssertionError('No orders should be posted')
                if path=='/api/v5/market/ticker':
                    return [{'instId':'SOXL-USDT-SWAP','last':'100','bidPx':'99.99',
                             'askPx':'100.01','volCcy24h':'1000000','ts':str(now)}]
                if path=='/api/v5/public/instruments':
                    return [{'instId':'SOXL-USDT-SWAP','state':'live',
                             'instCategory':'3','ctType':'linear',
                             'settleCcy':'USDT','ctValCcy':'SOXL','lever':'50'}]
                raise AssertionError(path)
        with self.assertRaisesRegex(CandidateRejected,'pre-market contract'):
            market_preflight(Equity(),{'symbol':'SOXL-USDT-SWAP','quote_price':100})

class OnePositionFullMarginThirtySecondTests(unittest.TestCase):
    def test_single_full_margin_live_mode_is_explicitly_armed(self):
        from trading.okx_live_executor import check_mode, ExecutionBlocked
        env={'OKX_CAPITAL_MODE':'full_margin',
             'OKX_MAX_ACTIVE_POSITIONS':'1',
             'OKX_FULL_MARGIN_ARM':FULL_MARGIN_ARM,
             'OKX_EXECUTION_ARM':MODE_ARM['live'],
             'OKX_ENABLE_REAL_TRADING':'YES','OKX_STOP_CONTINUOUS':'NO',
             'OKX_API_KEY':'TEST','OKX_SECRET_KEY':'TEST','OKX_PASSPHRASE':'TEST'}
        check_mode('live',env)
        with self.assertRaisesRegex(ExecutionBlocked,'separately armed'):
            check_mode('live',{**env,'OKX_FULL_MARGIN_ARM':''})
        with self.assertRaisesRegex(ExecutionBlocked,'adaptive_guarded'):
            check_mode('live',{**env,'OKX_MAX_ACTIVE_POSITIONS':'2'})
        with self.assertRaisesRegex(ExecutionBlocked,'Maximum open positions'):
            check_mode('live',{**env,'OKX_MAX_ACTIVE_POSITIONS':'11'})

    def test_liquidation_does_not_get_cooldown_exemption(self):
        from trading.okx_live_executor import enforce_exit_cooldown, ExecutionBlocked
        class History:
            def request(self,method,path,params=None):
                return [{'instType':'SWAP','type':'3','uTime':'1800000000000'}]
        with self.assertRaises(ExecutionBlocked):
            enforce_exit_cooldown(History(),now_ms=1800000000000+10000)

class FullUniverseCompletenessGateTests(unittest.TestCase):
    def test_live_report_must_include_all_liquid_candidates_with_no_scan_errors(self):
        from trading.okx_live_executor import read_report, ExecutionBlocked
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from datetime import datetime,timezone
        now=int(time.time()*1000)
        sample={'mode':'SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY',
                'core_specialist_agents':6,'advanced_quant_systems':7,
                'utc_timestamp':datetime.fromtimestamp(now/1000,timezone.utc).isoformat(),
                'errors':[],'results':[],
                'all_eligible_batch':True,'market_scan_complete':True,
                'markets_selected':10,'markets_analyzed':9,
                'markets_screened_for_liquidity':227}
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'r.json'
            path.write_text(json.dumps(sample))
            with self.assertRaisesRegex(ExecutionBlocked,'Incomplete full-universe'):
                read_report(path,now_ms=now)
            sample['markets_analyzed']=10
            path.write_text(json.dumps(sample))
            self.assertTrue(read_report(path,now_ms=now)['market_scan_complete'])
            sample['errors']=[{'symbol':'BTC-USDT-SWAP','reason':'timeout'}]
            path.write_text(json.dumps(sample))
            with self.assertRaisesRegex(ExecutionBlocked,'data errors'):
                read_report(path,now_ms=now)
