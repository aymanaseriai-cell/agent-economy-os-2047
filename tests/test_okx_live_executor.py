import hashlib
import hmac
import json
import time
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from trading.okx_live_executor import (
    MODE_ARM, OKX, ExecutionBlocked, check_mode, read_report, choose_signal,
    floor_step, contract_size, get_prices, client_order_id, daily_order_limit, execute,
)


def make_signal():
    now=int(time.time()*1000)
    return {
      'symbol':'BTC-USDT-SWAP','quote_price':100.0,'signal':'LONG',
      'last_complete_15m_candle_ms':now-60*1000,
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
