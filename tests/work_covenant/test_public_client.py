import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'examples' / 'work-covenant-client'))
import client as sdk

CID = 'a' * 64
PROOF = 'b' * 64
DEMO = {'ok':True,'contract_id':CID,'contract':{'task':{'title':'Public demo'},'criteria':[{'id':'file_ok','type':'artifact_exists','artifact':'report.json'}]},'sample_submission':{'artifacts':[{'name':'report.json','content':'public'}]}}
RESULT = {'ok':True, 'contract_id':CID,'proof_id':PROOF,'status':'local_checks_passed','buyer_acceptance_verified':False,'payment_verified':False,'onchain_settlement_verified':False,'evidence_covers_supplied_bytes_only':True,'results':[{'id':'file_ok','pass':True}]}

class FakeResponse(io.BytesIO):
    def __init__(self,payload,status=200,declared=None):
        b=json.dumps(payload).encode() if not isinstance(payload,bytes) else payload
        super().__init__(b)
        self.status=status
        self.headers={'Content-Length':str(declared if declared is not None else len(b))}
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class FakeOpener:
    def __init__(self, replies):self.replies=list(replies);self.calls=[]
    def open(self, req, timeout):
        self.calls.append((req.full_url,req.get_method(),req.data,timeout))
        return FakeResponse(self.replies.pop(0))

class ClientTests(unittest.TestCase):
    def test_live_example_happy_path(self):
        fake=FakeOpener([DEMO,RESULT]);report=sdk.run_live(opener=fake)
        self.assertTrue(report['demo_only'])
        self.assertEqual(report['checks_passed'],1)
        self.assertFalse(report['buyer_acceptance_verified'])
        self.assertFalse(report['payment_verified'])
        self.assertEqual(len(fake.calls),2)
        self.assertTrue(fake.calls[0][0].startswith(sdk.GATEWAY))
        self.assertEqual([x[1] for x in fake.calls],['GET','POST'])
        self.assertNotIn(b'authorization',fake.calls[1][2])
    def test_bad_contract_id_rejected(self):
        bad=dict(DEMO,contract_id='invalid')
        with self.assertRaises(sdk.DemoError): sdk.run_live(opener=FakeOpener([bad]))
    def test_mismatched_contract_rejected(self):
        bad=dict(RESULT,contract_id='c'*64)
        with self.assertRaises(sdk.DemoError):sdk.run_live(opener=FakeOpener([DEMO,bad]))
    def test_payment_verified_true_rejected(self):
        bad=dict(RESULT,payment_verified=True)
        with self.assertRaises(sdk.DemoError):sdk.run_live(opener=FakeOpener([DEMO,bad]))
    def test_buyer_acceptance_claim_rejected(self):
        bad=dict(RESULT,buyer_acceptance_verified=True)
        with self.assertRaises(sdk.DemoError):sdk.run_live(opener=FakeOpener([DEMO,bad]))
    def test_missing_evidence_limitation_rejected(self):
        bad=dict(RESULT,evidence_covers_supplied_bytes_only=False)
        with self.assertRaises(sdk.DemoError):sdk.run_live(opener=FakeOpener([DEMO,bad]))
    def test_failed_checks_rejected(self):
        bad=dict(RESULT,results=[{'pass':False}])
        with self.assertRaises(sdk.DemoError):sdk.run_live(opener=FakeOpener([DEMO,bad]))
    def test_oversized_response_rejected(self):
        with self.assertRaises(sdk.DemoError):sdk.json_request('/demo',opener=FakeOpener([b'a'*(sdk.MAX_RESPONSE+1)]))
    def test_invalid_json_rejected(self):
        with self.assertRaises(sdk.DemoError):sdk.json_request('/demo',opener=FakeOpener([b'not json']))
    def test_invalid_url_path_and_origin_rejected(self):
        for path,origin in [('/x402/settle','gateway'),('/demo','evil'),('https://evil.tld','gateway')]:
            with self.subTest(path=path,origin=origin),self.assertRaises(sdk.DemoError):
                sdk.json_request(path,origin=origin)
    def test_no_redirect(self):
        with self.assertRaises(sdk.DemoError):
            sdk.NoRedirects().redirect_request(None,None,302,'redirect',{},'https://evil.example')
    def test_payload_cannot_be_sent_to_get(self):
        with self.assertRaises(sdk.DemoError):sdk.json_request('/demo',payload={'x':1})
    def test_missing_payload_on_post(self):
        with self.assertRaises(sdk.DemoError):sdk.json_request('/v1/evaluate')
    def test_oversize_request(self):
        with self.assertRaises(sdk.DemoError):sdk.json_request('/v1/evaluate',payload={'huge':'x'*20000})
    def test_dry_run_has_no_network(self):
        p=subprocess.run([sys.executable,str(Path(sdk.__file__))],capture_output=True,text=True,env={**os.environ})
        self.assertEqual(p.returncode,0)
        self.assertFalse(json.loads(p.stdout)['network_requests_made'])

if __name__=='__main__':unittest.main()
