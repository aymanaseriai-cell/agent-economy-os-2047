"""No-order recovery for public exchange glitches, fail closed for others."""
import subprocess
import unittest
from unittest.mock import patch
from trading.okx_five_second_worker import loop


def done(cmd, code=0, out=""):
    return subprocess.CompletedProcess(cmd,code,out,"")


class PublicScanWorkerRecoveryTests(unittest.TestCase):
    def test_one_transient_50026_skips_executor_then_full_fresh_scan(self):
        calls=[];pauses=[];t=[0.]
        def run(cmd,timeout):
            calls.append(cmd[2])
            if cmd[2]=="trading.six_agent_council" and calls.count(cmd[2])==1:
                return done(cmd,75,"TITAN PUBLIC GET TRANSIENT_NO_ORDERS\n")
            if cmd[2]=="trading.okx_live_executor":
                return done(cmd,0,"OKX EXECUTION RESULT: NO_CONSENSUS\n")
            return done(cmd)
        def sleep(secs):
            pauses.append(secs);t[0]+=secs
        self.assertEqual(loop(max_cycles=2,run=run,clock=lambda:t[0],sleep=sleep),0)
        self.assertEqual(calls,["trading.six_agent_council","trading.six_agent_council",
                                "trading.okx_live_executor"])
        self.assertEqual(pauses,[5])

    def test_four_consecutive_transient_scans_stop_without_any_order(self):
        calls=[];delays=[];t=[0.]
        def run(cmd,timeout):
            calls.append(cmd[2])
            return done(cmd,75,"TITAN PUBLIC GET TRANSIENT_NO_ORDERS\n")
        def sleep(secs):
            delays.append(secs);t[0]+=secs
        self.assertEqual(loop(max_cycles=10,run=run,clock=lambda:t[0],sleep=sleep),2)
        self.assertEqual(calls,["trading.six_agent_council"]*4)
        self.assertEqual(delays,[5,10,20])

    def test_unverified_transient_exit_cannot_resume_trade(self):
        calls=[]
        def run(cmd,timeout):
            calls.append(cmd[2])
            return done(cmd,75,"not-a-valid-public-retry-marker\n")
        self.assertEqual(loop(max_cycles=5,run=run,clock=lambda:0.,
                              sleep=lambda _:None),2)
        self.assertEqual(calls,["trading.six_agent_council"])

    def test_other_scan_failure_stops_without_executor(self):
        calls=[]
        def run(cmd,timeout):
            calls.append(cmd[2])
            return done(cmd,2,"DATA ERROR malformed TP/SL")
        self.assertEqual(loop(max_cycles=5,run=run,clock=lambda:0.,
                              sleep=lambda _:None),2)
        self.assertEqual(calls,["trading.six_agent_council"])

    def test_transient_scan_does_not_override_bounded_deadline(self):
        calls=[];t=[0.]
        def run(cmd,timeout):
            calls.append(cmd[2])
            t[0]=240
            return done(cmd,75,"TITAN PUBLIC GET TRANSIENT_NO_ORDERS\n")
        with patch.dict("os.environ",{"OKX_AUTOREENTRY_ENABLED":"YES"}):
            code=loop(max_runtime_seconds=245,run=run,
                      clock=lambda:t[0],sleep=lambda x:None)
        self.assertEqual(code,0)
        self.assertEqual(calls,["trading.six_agent_council"])


    def test_phoenix_recovers_from_four_public_only_outages_then_no_consensus(self):
        from trading.okx_five_second_worker import MAX_PUBLIC_RECOVERY_BURSTS
        self.assertEqual(MAX_PUBLIC_RECOVERY_BURSTS,2)
        calls=[];pauses=[];t=[0.]
        def run(cmd,timeout):
            component=cmd[2]
            calls.append(component)
            if component=="trading.six_agent_council" and calls.count(component)<=4:
                return done(cmd,75,"TITAN PUBLIC GET TRANSIENT_NO_ORDERS\n")
            if component=="trading.okx_live_executor":
                return done(cmd,0,"OKX EXECUTION RESULT: NO_CONSENSUS\n")
            return done(cmd)
        def sleep(sec):
            pauses.append(sec);t[0]+=sec
        with patch.dict("os.environ",{"OKX_PUBLIC_RECOVERY_ENABLED":"YES"}):
            result=loop(max_cycles=5,run=run,clock=lambda:t[0],sleep=sleep)
        self.assertEqual(result,0)
        self.assertEqual(calls.count("trading.six_agent_council"),5)
        self.assertEqual(calls.count("trading.okx_live_executor"),1)
        self.assertEqual(pauses,[5,10,20,30])

    def test_phoenix_never_retries_unverified_public_error(self):
        calls=[]
        def run(cmd,timeout):
            calls.append(cmd[2])
            return done(cmd,75,"not-a-verified-PUBLIC-only-error\n")
        with patch.dict("os.environ",{"OKX_PUBLIC_RECOVERY_ENABLED":"YES"}):
            self.assertEqual(loop(max_cycles=15,run=run,clock=lambda:0.,
                                  sleep=lambda _:None),2)
        self.assertEqual(calls,["trading.six_agent_council"])

    def test_phoenix_bounded_two_bursts_then_stops(self):
        calls=[];pauses=[];t=[0.]
        def run(cmd,timeout):
            calls.append(cmd[2])
            return done(cmd,75,"TITAN PUBLIC GET TRANSIENT_NO_ORDERS\n")
        def sleep(seconds):
            pauses.append(seconds);t[0]+=seconds
        with patch.dict("os.environ",{"OKX_PUBLIC_RECOVERY_ENABLED":"YES"}):
            result=loop(max_cycles=20,run=run,clock=lambda:t[0],sleep=sleep)
        self.assertEqual(result,2)
        self.assertEqual(calls,["trading.six_agent_council"]*12)
        self.assertEqual(pauses,[5,10,20,30,5,10,20,60,5,10,20])

    def test_phoenix_cannot_restart_after_private_executor_failure(self):
        calls=[]
        def run(cmd,timeout):
            calls.append(cmd[2])
            if cmd[2]=="trading.okx_live_executor":
                return done(cmd,3,"")
            return done(cmd)
        with patch.dict("os.environ",{"OKX_PUBLIC_RECOVERY_ENABLED":"YES"}):
            result=loop(max_cycles=10,run=run,clock=lambda:0.,sleep=lambda _:None)
        self.assertEqual(result,3)
        self.assertEqual(calls,["trading.six_agent_council",
                                "trading.okx_live_executor"])

if __name__ == "__main__":
    unittest.main()
