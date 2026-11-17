"""Proof-pin prevents model, configuration, and historical OHLC from arming live."""
import hashlib,json,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from trading.titan_profit_first_gate import (
    REVIEWED_PROOF_SHA256,KIND,validate_proof,permitted_new_live_entry
)
class TestProfitFirst(unittest.TestCase):
    def fixture(self):
        now=datetime(2026,11,17,12,tzinfo=timezone.utc)
        p=dict(mode=KIND,untouched_forward_samples=True,
               independently_reconciled_fill_receipts=True,
               realized_fees_and_funding_reconciled=True,
               tiny_equity_exchange_lots_verified=True,
               liquidation_sensitivity_verified=True,
               stress_slippage_and_fees_verified=True,
               number_of_future_fills=210,distinct_trading_days=34,
               net_return_after_costs_pct=8,
               stress_net_return_after_costs_pct=3,
               daily_net_95pct_lower_bound_usdt=.0001,
               max_drawdown_pct=9,
               start_utc=(now-timedelta(days=40)).isoformat(),
               end_utc=(now-timedelta(days=2)).isoformat(),
               generated_utc=(now-timedelta(days=1)).isoformat())
        return p,now
    def test_unapproved_mode_stays_flat(self):
        self.assertEqual(REVIEWED_PROOF_SHA256,"")
        self.assertFalse(permitted_new_live_entry())
    def test_reviewed_positive_future_proof_may_eventually_pass(self):
        p,now=self.fixture()
        raw=json.dumps(p).encode()
        self.assertTrue(validate_proof(raw,hashlib.sha256(raw).hexdigest(),now=now))
    def test_negative_or_too_small_evidence_fails(self):
        p,now=self.fixture()
        for key,value in (("number_of_future_fills",34),
                         ("stress_net_return_after_costs_pct",-.01),
                         ("daily_net_95pct_lower_bound_usdt",-1),
                         ("tiny_equity_exchange_lots_verified",False),
                         ("mode","OFFLINE_RESEARCH_NO_ORDERS")):
            wrong={**p,key:value}
            raw=json.dumps(wrong).encode()
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_proof(raw,hashlib.sha256(raw).hexdigest(),now=now)
    def test_modified_proof_cannot_reuse_reviewed_digest(self):
        p,now=self.fixture()
        raw=json.dumps(p).encode()
        digest=hashlib.sha256(raw).hexdigest()
        p["net_return_after_costs_pct"]=99
        with self.assertRaises(ValueError):
            validate_proof(json.dumps(p).encode(),digest,now=now)
    def test_file_itself_cannot_arm_absent_pinned_digest(self):
        p,now=self.fixture()
        with TemporaryDirectory() as td:
            path=Path(td)/"proof.json"
            path.write_text(json.dumps(p))
            self.assertFalse(permitted_new_live_entry(path=path,now=now))
if __name__=="__main__":unittest.main()
