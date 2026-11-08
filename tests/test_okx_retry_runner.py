import subprocess
import unittest
from trading.okx_retry_runner import retry_scans

def completed(args, returncode, status=""):
    return subprocess.CompletedProcess(args,returncode,
        "OKX EXECUTION RESULT: "+status+"\n" if status else "", "")

class RetryScanningTests(unittest.TestCase):
    def test_no_consensus_waits_exactly_five_seconds_between_full_scans(self):
        calls=[];pauses=[];clock=[0.0]
        def run(args,timeout=None):
            calls.append((args,timeout))
            return completed(args,0,"NO_CONSENSUS") if args[2]=="trading.okx_live_executor" else completed(args,0)
        def sleep(n):
            pauses.append(n);clock[0]+=n
        self.assertEqual(retry_scans(max_cycles=4,delay_seconds=5,window_seconds=100,
            run=run,clock=lambda:clock[0],sleep=sleep),0)
        self.assertEqual(len(calls),8)
        self.assertEqual(pauses,[5,5,5])
        self.assertEqual(sum("six_agent_council" in x[0][2] for x in calls),4)

    def test_order_or_action_outcome_stops_immediately(self):
        calls=[];pauses=[]
        def run(args,timeout=None):
            calls.append(args)
            return completed(args,0,"ORDER_CONFIRMED") if args[2]=="trading.okx_live_executor" else completed(args,0)
        self.assertEqual(retry_scans(max_cycles=8,run=run,clock=lambda:0,sleep=pauses.append),0)
        self.assertEqual(len(calls),2)
        self.assertEqual(pauses,[])

    def test_executor_block_prevents_any_retry(self):
        calls=[]
        def run(args,timeout=None):
            calls.append(args)
            return completed(args,2) if args[2]=="trading.okx_live_executor" else completed(args,0)
        self.assertEqual(retry_scans(max_cycles=8,run=run,clock=lambda:0,sleep=lambda _:None),2)
        self.assertEqual(len(calls),2)

    def test_failed_market_scan_prevents_execution(self):
        calls=[]
        def run(args,timeout=None):
            calls.append(args)
            return completed(args,124)
        self.assertEqual(retry_scans(max_cycles=8,run=run,clock=lambda:0,sleep=lambda _:None),2)
        self.assertEqual(len(calls),1)

    def test_missing_executor_status_does_not_retry(self):
        calls=[]
        def run(args,timeout=None):
            calls.append(args)
            return completed(args,0)
        self.assertEqual(retry_scans(max_cycles=8,run=run,clock=lambda:0,sleep=lambda _:None),0)
        self.assertEqual(len(calls),2)

    def test_bounded_window_stops_after_first_long_scan(self):
        calls=[];clock=[0.0];pauses=[]
        def run(args,timeout=None):
            calls.append(args)
            if args[2]=="trading.six_agent_council":clock[0]+=30
            return completed(args,0,"NO_CONSENSUS") if args[2]=="trading.okx_live_executor" else completed(args,0)
        self.assertEqual(retry_scans(max_cycles=8,window_seconds=45,
               run=run,clock=lambda:clock[0],sleep=pauses.append),0)
        self.assertEqual(len(calls),2)
        self.assertEqual(pauses,[])

    def test_invalid_settings_rejected(self):
        with self.assertRaises(ValueError):
            retry_scans(max_cycles=0)
        with self.assertRaises(ValueError):
            retry_scans(delay_seconds=0)
        with self.assertRaises(ValueError):
            retry_scans(window_seconds=10)
