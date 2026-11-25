import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'buyer-gate/check.py'
SCHEMA = 'agent-economy.buyer-gate/1'

class DecimalIntegration(unittest.TestCase):
    def run_case(self, expected, delivered, wanted, *, bad_pin=False):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            policy = p / 'policy.json'
            policy.write_text('{"schema":"'+SCHEMA+'","requirements":[{"id":"numeric_check","type":"json_pointer_equals","path":"out.json","pointer":"/v","expected":'+expected+'}]}', encoding='utf-8')
            (p / 'out.json').write_text('{"v":'+delivered+'}', encoding='utf-8')
            pin = '0'*64 if bad_pin else hashlib.sha256(policy.read_bytes()).hexdigest()
            env = dict(os.environ); env.pop('GITHUB_STEP_SUMMARY',None)
            r = subprocess.run([sys.executable,str(SCRIPT),str(policy),'--root',str(p),'--policy-sha256',pin,'--json-out',str(p/'result.json')],capture_output=True,text=True,timeout=5,env=env)
            self.assertEqual(r.stderr,'')
            result = json.loads(r.stdout)
            self.assertEqual(result,json.loads((p/'result.json').read_text()))
            self.assertEqual((r.returncode,result['local_checks_passed']),(0 if wanted else 1,wanted))
            for key in ('buyer_identity_verified','buyer_authority_verified','agent_execution_verified','source_freshness_verified','independent_provenance_verified','payment_verified'):
                self.assertIs(result[key],False)
            return result
    def test_decimal_rounding(self): self.run_case('0.1','0.10000000000000001',False)
    def test_integer_precision_in_decimal(self): self.run_case('9007199254740992.0','9007199254740993.0',False)
    def test_underflow_not_zero(self): self.run_case('0.0','1e-400',False)
    def test_distinct_tiny_decimals(self): self.run_case('1e-400','2e-400',False)
    def test_equal_tiny_decimals(self): self.run_case('1e-400','10e-401',True)
    def test_equal_decimal_notation(self): self.run_case('0.10000000000000001','0.100000000000000010',True)
    def test_equal_exponent(self): self.run_case('1.00','1e0',True)
    def test_decimal_integer_boundary(self): self.run_case('1','1.0',False)
    def test_boolean_integer_boundary(self): self.run_case('true','1',False)
    def test_signed_zero(self): self.run_case('-0.0','0.0',True)
    def test_nan(self): self.run_case('0.0','NaN',False)
    def test_overflow(self): self.run_case('0.0','1e309',False)
    def test_infinity(self): self.run_case('0.0','Infinity',False)
    def test_string_number_boundary(self): self.run_case('"1"','1',False)
    def test_null(self): self.run_case('null','null',True)
    def test_null_number(self): self.run_case('null','0',False)
    def test_duplicate_artifact(self): self.run_case('1.0','0.0,"v":1.0',False)
    def test_wrong_policy_pin(self): self.run_case('1.0','1.0',False,bad_pin=True)
    def test_long_decimal(self): self.run_case('0.0','0.'+'0'*4096,False)
    def test_huge_negative_exponent(self): self.run_case('0.0','1e-999999999999999999999999999999999',False)
    def test_decimal_against_json_object(self): self.run_case('1.0','{"v":1.0}',False)

if __name__ == '__main__': unittest.main()
