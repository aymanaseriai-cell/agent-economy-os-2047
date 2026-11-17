import copy,gzip,hashlib,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine,auditor
DATA=Path(__file__).resolve().parents[1]/'titan6h-okx-5m-20261117.zip'
RESULT=Path(__file__).resolve().parents[1]/'grid-results.json.gz'

class HighLeverageResearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m,cls.market,cls.clock=engine.load(DATA)
        cls.res=json.loads(gzip.decompress(RESULT.read_bytes()))
    def test_source_sha_and_alignment(self):
        self.assertEqual(len(self.market),6)
        self.assertEqual(len(self.clock),3455)
        self.assertTrue(all(v['gaps']==0 for v in self.m['records'].values()))
    def test_lot_sizing_not_fractional_fantasy(self):
        sym='ETH-USDT-SWAP';q,n,margin,error=engine.contract_size(self.m,sym,4.15,2000,100,'base')
        self.assertIsNone(error)
        self.assertEqual((engine.Decimal(str(q))%engine.Decimal(self.m['specs'][sym]['lotSz'])),0)
        self.assertLess(margin,4.15)
    def test_leverage_caps(self):
        self.assertEqual(engine.min_max_leverage(self.m,'DOGE-USDT-SWAP'),50.)
        self.assertEqual(engine.contract_size(self.m,'DOGE-USDT-SWAP',4.15,.15,100,'base')[-1],'leverage_cap')
    def test_adaptive_rejects_no_edge(self):
        x={'sym':'ETH-USDT-SWAP','sigma':.0001,'volume_usdt':1e8}
        self.assertIsNone(engine.adaptive_leverage_optimizer(self.m,x,4.15,2000,'base',[.01]*15))
        self.assertIsNone(engine.adaptive_leverage_optimizer(self.m,x,4.15,2000,'base',[-.01]*50))
    def test_adaptive_accepts_positive_fixture(self):
        x={'sym':'ETH-USDT-SWAP','sigma':.0001,'volume_usdt':1e8}
        self.assertIn(engine.adaptive_leverage_optimizer(self.m,x,4.15,2000,'base',[.015+(.0001 if i%2 else -.0001) for i in range(50)]),engine.LEVERAGES)
    def test_end_six_hours_all_closed(self):
        s=engine.starts(self.clock)[8]
        b=engine.simulation(self.m,self.market,self.clock,s,50,'shock_continuation')
        self.assertEqual(b['end_ts']-b['start_ts'],6*3600*1000)
        self.assertTrue(all(p['exit_ts']<=b['end_ts'] for p in b['ledger']))
    def test_all_windows_are_retained(self):
        self.assertEqual(len(self.res['starts_utc_ms']),47)
        self.assertEqual(len(self.res['grid_ledgers']),48)
        self.assertTrue(all(len(w)==47 for w in self.res['grid_ledgers'].values()))
        self.assertEqual(sum(v['successes'] for v in self.res['grid_scores'].values()),0)
    def test_independent_audit(self):
        self.assertTrue(auditor.audit(DATA,RESULT)['passed'])
    def test_reject_balance_falsification(self):
        x=copy.deepcopy(self.res);w=x['grid_ledgers'][next(iter(x['grid_ledgers']))][0]
        w['final_usdt']+=4.15
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'fake.json';f.write_text(json.dumps(x))
            a=auditor.audit(DATA,f)
            self.assertFalse(a['passed'])
            self.assertTrue(any('FALSE_FINAL_BALANCE' in e for e in a['faults']))
    def test_reject_future_signal(self):
        x=copy.deepcopy(self.res)
        for windows in x['grid_ledgers'].values():
            alltrades=[t for w in windows for t in w['ledger']]
            if alltrades:
                alltrades[0]['signal_ts']+=300000;break
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'fake.json';f.write_text(json.dumps(x))
            self.assertFalse(auditor.audit(DATA,f)['passed'])
    def test_reject_illegal_contract(self):
        x=copy.deepcopy(self.res)
        for windows in x['grid_ledgers'].values():
            alltrades=[t for w in windows for t in w['ledger']]
            if alltrades:
                alltrades[0]['q']+=0.000001;break
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'fake.json';f.write_text(json.dumps(x))
            self.assertFalse(auditor.audit(DATA,f)['passed'])
    def test_reject_data_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'tamper.zip'
            with zipfile.ZipFile(DATA) as src,zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as out:
                for name in src.namelist():
                    raw=src.read(name)
                    if name.endswith('ETH-USDT-SWAP-trade.json.gz'):
                        rows=json.loads(gzip.decompress(raw));rows[50][4]=str(float(rows[50][4])*1.01)
                        raw=gzip.compress(json.dumps(rows).encode())
                    out.writestr(name,raw)
            with self.assertRaisesRegex(ValueError,'SOURCE_SHA_MISMATCH'):engine.load(p)
    def test_no_trade_api(self):
        for f in ('engine.py','auditor.py'):
            data=(RESULT.parent/f).read_text()
            self.assertNotIn('/api/v5/trade/order',data)
            self.assertNotIn('OKX_API_KEY',data)

if __name__=='__main__':unittest.main()

