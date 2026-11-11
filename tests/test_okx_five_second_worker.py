import os
import subprocess
from unittest.mock import patch
import unittest

from trading.okx_five_second_worker import loop

def done(cmd, status=None, code=0):
    output=("OKX EXECUTION RESULT: "+status+"\n") if status else ""
    return subprocess.CompletedProcess(cmd,code,output,"")

class FiveSecondWorkerTests(unittest.TestCase):
    def test_five_second_pause_after_every_completed_no_consensus(self):
        calls=[];pauses=[]; now=[0.]
        def run(args,timeout):
            calls.append((args,timeout))
            return done(args,"NO_CONSENSUS") if args[2]=="trading.okx_live_executor" else done(args)
        def sleep(seconds):
            pauses.append(seconds);now[0]+=seconds
        self.assertEqual(loop(max_cycles=4,run=run,
                              clock=lambda:now[0],sleep=sleep),0)
        self.assertEqual(len(calls),8)
        self.assertEqual(pauses,[5,5,5])
        self.assertEqual(sum(x[0][2]=="trading.six_agent_council" for x in calls),4)


    def test_recurring_live_rotates_liquid_markets_without_changing_executor(self):
        calls=[]
        clock=[0.]
        def run(args,timeout):
            calls.append(args)
            if args[2]=="trading.okx_resume_monitor":
                return subprocess.CompletedProcess(args,0,"OKX MONITOR RESULT: FLAT_ELIGIBLE\n","")
            if args[2]=="trading.okx_live_executor":
                return done(args,"NO_CONSENSUS")
            return done(args)
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES"}):
            self.assertEqual(loop(max_cycles=1,top=12,
                                  resume_after_protected_fill=True,
                                  run=run,clock=lambda:clock[0],
                                  sleep=lambda n:clock.__setitem__(0,clock[0]+n)),0)
        scans=[cmd for cmd in calls if cmd[2]=="trading.six_agent_council"]
        self.assertEqual(len(scans),1)
        self.assertIn("--rotate-universe",scans[0])
        self.assertEqual(sum(cmd[2]=="trading.okx_live_executor" for cmd in calls),1)

    def test_twenty_coin_scan_is_allowed_and_still_uses_same_guarded_executor(self):
        calls=[]
        def run(args,timeout):
            calls.append(args)
            return done(args,"NO_CONSENSUS") if args[2]=="trading.okx_live_executor" else done(args)
        self.assertEqual(loop(max_cycles=1,top=20,run=run,
                              clock=lambda:0.,sleep=lambda _:None),0)
        self.assertIn("20",calls[0])
        self.assertEqual([x[2] for x in calls],
                         ["trading.six_agent_council","trading.okx_live_executor"])

    def test_dry_run_signal_continues_research_without_order(self):
        calls=[]; pauses=[]
        def run(args,timeout):
            calls.append(args)
            return done(args,"DRY_RUN_SIGNAL_ONLY") if args[2]=="trading.okx_live_executor" else done(args)
        self.assertEqual(loop(max_cycles=3,run=run,
                              clock=lambda:0.,sleep=pauses.append),0)
        self.assertEqual(pauses,[5,5])
        self.assertEqual(len(calls),6)

    def test_any_order_outcome_stops_to_prevent_duplicates(self):
        calls=[]; pauses=[]
        def run(args,timeout):
            calls.append(args)
            return done(args,"FILLED_PROTECTED") if args[2]=="trading.okx_live_executor" else done(args)
        self.assertEqual(loop(max_cycles=10,run=run,
                              clock=lambda:0.,sleep=pauses.append),0)
        self.assertEqual(len(calls),2)
        self.assertEqual(pauses,[])

    def test_exchange_error_never_retries_order(self):
        calls=[]
        def run(args,timeout):
            calls.append(args)
            return done(args,code=2) if args[2]=="trading.okx_live_executor" else done(args)
        self.assertEqual(loop(max_cycles=10,run=run,clock=lambda:0.,
                              sleep=lambda _:None),2)
        self.assertEqual(len(calls),2)

    def test_failed_market_data_stops_before_executor(self):
        calls=[]
        def run(args,timeout):
            calls.append(args)
            return done(args,code=124)
        self.assertEqual(loop(max_cycles=10,run=run,clock=lambda:0.,
                              sleep=lambda _:None),2)
        self.assertEqual(len(calls),1)

    def test_ambiguous_and_missing_status_fail_closed(self):
        for stdout in ("", "OKX EXECUTION RESULT: NO_CONSENSUS\nOKX EXECUTION RESULT: NO_CONSENSUS\n"):
            calls=[]
            def run(args,timeout):
                calls.append(args)
                if args[2]=="trading.okx_live_executor":
                    return subprocess.CompletedProcess(args,0,stdout,"")
                return done(args)
            self.assertEqual(loop(max_cycles=10,run=run,clock=lambda:0.,
                                  sleep=lambda _:None),3)
            self.assertEqual(len(calls),2)

    def test_bounded_job_window(self):
        calls=[];now=[0.];pauses=[]
        def run(args,timeout):
            calls.append(args)
            if args[2]=="trading.six_agent_council":
                now[0]+=40
                return done(args)
            return done(args,"NO_CONSENSUS")
        def sleep(n):pauses.append(n);now[0]+=n
        self.assertEqual(loop(max_runtime_seconds=100,run=run,clock=lambda:now[0],sleep=sleep),0)
        self.assertEqual(sum(x[2]=="trading.six_agent_council" for x in calls),2)
        self.assertEqual(pauses,[5])

    def test_public_window_finishes_without_starting_too_late_scan(self):
        now=[0.0]; calls=[]
        def run(args,timeout):
            calls.append((args[2],timeout))
            if args[2]=="trading.six_agent_council":
                now[0]+=23
                return done(args)
            return done(args,"DRY_RUN_SIGNAL_ONLY")
        def sleep(n): now[0]+=n
        with patch.dict(os.environ,{"OKX_EXECUTION_MODE":"dry_run",
                                    "OKX_ENABLE_REAL_TRADING":"NO"}):
            code=loop(max_runtime_seconds=100,graceful_public_deadline=True,
                      run=run,clock=lambda:now[0],sleep=sleep)
        self.assertEqual(code,0)
        self.assertEqual(sum(c[0]=="trading.six_agent_council" for c in calls),3)
        self.assertEqual(sum(c[0]=="trading.okx_live_executor" for c in calls),3)

    def test_public_incomplete_last_scan_is_safe_deadline_not_failed_job(self):
        now=[0.0]; calls=[]
        def run(args,timeout):
            calls.append((args[2],timeout))
            if args[2]=="trading.six_agent_council":
                if len(calls)>2:
                    # Deadline-limited scan ends before any order executor.
                    self.assertLess(timeout,90)
                    now[0]+=timeout
                    return done(args,code=124)
                now[0]+=40
                return done(args)
            return done(args,"DRY_RUN_SIGNAL_ONLY")
        def sleep(n):now[0]+=n
        with patch.dict(os.environ,{"OKX_EXECUTION_MODE":"dry_run",
                                    "OKX_ENABLE_REAL_TRADING":"NO"}):
            code=loop(max_runtime_seconds=100,graceful_public_deadline=True,
                      run=run,clock=lambda:now[0],sleep=sleep)
        self.assertEqual(code,0)
        self.assertEqual([c[0] for c in calls].count("trading.okx_live_executor"),1)

    def test_public_scan_failure_with_full_time_budget_remains_failure(self):
        calls=[]
        def run(args,timeout):
            calls.append((args[2],timeout))
            return done(args,code=124)
        with patch.dict(os.environ,{"OKX_EXECUTION_MODE":"dry_run",
                                    "OKX_ENABLE_REAL_TRADING":"NO"}):
            code=loop(max_runtime_seconds=270,graceful_public_deadline=True,
                      run=run,clock=lambda:0.0,sleep=lambda _:None)
        self.assertEqual(code,2)
        self.assertEqual(calls,[("trading.six_agent_council",90)])

    def test_public_deadline_refuses_any_live_or_unbounded_configuration(self):
        calls=[]
        def never_run(*args,**kwargs):
            calls.append(args)
            self.fail("Unsafe research deadline mode reached market or order calls")
        for mode,enable,runtime in (("live","YES",270),
                                    ("dry_run","YES",270),
                                    ("live","NO",270),
                                    ("dry_run","NO",0)):
            with self.subTest(mode=mode,enable=enable,runtime=runtime):
                with patch.dict(os.environ,{"OKX_EXECUTION_MODE":mode,
                                            "OKX_ENABLE_REAL_TRADING":enable}):
                    with self.assertRaises(ValueError):
                        loop(max_runtime_seconds=runtime,
                             graceful_public_deadline=True,run=never_run)
        self.assertEqual(calls,[])

    def test_refuse_faster_than_five_seconds(self):
        with self.assertRaises(ValueError):loop(interval_seconds=1)
        with self.assertRaises(ValueError):loop(interval_seconds=10)
        with self.assertRaises(ValueError):loop(top=21)
        with self.assertRaises(ValueError):loop(max_cycles=-1)
        with self.assertRaises(ValueError):loop(max_runtime_seconds=-1)

    def test_every_tick_uses_full_original_council_and_original_guarded_executor(self):
        calls=[]
        def run(args,timeout):
            calls.append(args)
            if args[2]=="trading.okx_live_executor": return done(args,"NO_CONSENSUS")
            return done(args)
        self.assertEqual(loop(max_cycles=1,top=6,
                              run=run,clock=lambda:0.,sleep=lambda _:None),0)
        self.assertEqual(calls[0][2:6],["trading.six_agent_council","--top","6","--out"])
        self.assertEqual(calls[1][2],"trading.okx_live_executor")

if __name__=="__main__":
    unittest.main()

class AutoResumeWorkerTests(unittest.TestCase):
    def test_protected_fill_switches_to_monitor_then_next_quant_trade(self):
        clock=[0.0]
        calls=[]; delays=[]
        monitor_states=iter(("FLAT_ELIGIBLE","POSITION_OPEN_PROTECTED","COOLDOWN_ACTIVE","FLAT_ELIGIBLE"))
        results=iter(("FILLED_PROTECTED","NO_CONSENSUS"))
        def fake_run(cmd,timeout):
            calls.append(cmd[2])
            if cmd[2]=="trading.okx_resume_monitor":
                return subprocess.CompletedProcess(cmd,0,
                       "OKX MONITOR RESULT: "+next(monitor_states)+"\n","")
            if cmd[2]=="trading.okx_live_executor":
                return done(cmd,next(results))
            return done(cmd)
        def sleep(seconds):
            delays.append(seconds);clock[0]+=seconds
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES",
                                    "OKX_CAPITAL_MODE":"guarded"}):
            result=loop(max_cycles=2,resume_after_protected_fill=True,
                        run=fake_run,clock=lambda:clock[0],sleep=sleep)
        self.assertEqual(result,0)
        self.assertEqual(calls.count("trading.okx_resume_monitor"),4)
        self.assertEqual(calls.count("trading.six_agent_council"),2)
        self.assertEqual(delays,[5,30,30])

    def test_first_fill_does_not_block_second_when_portfolio_has_free_slots(self):
        # Distinct from legacy single-position logic: with an existing
        # protected position and remaining slots, a second fresh signal is
        # allowed to reach the executor. No mocked order is actually sent.
        scans=[];clock=[0.];delays=[]
        monitor_states=iter(('FLAT_ELIGIBLE','PORTFOLIO_ELIGIBLE'))
        executor_results=iter(('FILLED_PROTECTED','NO_CONSENSUS'))
        def fake_run(cmd,timeout):
            scans.append(cmd[2])
            if cmd[2]=='trading.okx_resume_monitor':
                return subprocess.CompletedProcess(
                    cmd,0,
                    'OKX PORTFOLIO SLOTS: open=1 limit=10 remaining=9\\n'
                    'OKX MONITOR RESULT: '+next(monitor_states)+'\\n','')
            if cmd[2]=='trading.okx_live_executor':
                return done(cmd,next(executor_results))
            return done(cmd)
        def sleep(t): delays.append(t);clock[0]+=t
        with patch.dict(os.environ,{'OKX_AUTOREENTRY_ENABLED':'YES',
                                    'OKX_MAX_ACTIVE_POSITIONS':'10'}):
            result=loop(max_cycles=2,resume_after_protected_fill=True,
                        run=fake_run,clock=lambda:clock[0],sleep=sleep)
        self.assertEqual(result,0)
        self.assertEqual(scans.count('trading.okx_resume_monitor'),2)
        self.assertEqual(scans.count('trading.six_agent_council'),2)
        self.assertEqual(scans.count('trading.okx_live_executor'),2)
        self.assertEqual(delays,[5])

    def test_unprotected_open_position_stops_immediately(self):
        calls=[]
        def run(cmd,timeout):
            calls.append(cmd[2])
            return done(cmd,code=2)
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES",
                                    "OKX_CAPITAL_MODE":"guarded"}):
            self.assertEqual(loop(resume_after_protected_fill=True,run=run,
                                  clock=lambda:0.0),2)
        self.assertEqual(calls,["trading.okx_resume_monitor"])

    def test_auto_repeat_accepts_armed_full_margin_worker_mode(self):
        calls=[]
        def fake_run(cmd,timeout):
            calls.append(cmd[2])
            if cmd[2]=="trading.okx_resume_monitor":
                return subprocess.CompletedProcess(cmd,0,"OKX MONITOR RESULT: FLAT_ELIGIBLE\n","")
            if cmd[2]=="trading.okx_live_executor":
                return done(cmd,"NO_CONSENSUS")
            return done(cmd)
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES",
                                    "OKX_CAPITAL_MODE":"Full_margin"}):
            self.assertEqual(loop(max_cycles=1,resume_after_protected_fill=True,
                                  run=fake_run,clock=lambda:0.0),0)
        self.assertEqual(calls,["trading.okx_resume_monitor","trading.six_agent_council",
                                "trading.okx_live_executor"])

    def test_auto_repeat_still_requires_independent_opt_in(self):
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"NO",
                                    "OKX_CAPITAL_MODE":"Full_margin"}):
            with self.assertRaisesRegex(ValueError,"explicit"):
                loop(resume_after_protected_fill=True)

class CooldownRacingMonitorTests(unittest.TestCase):
    def test_cooldown_after_flat_monitor_continues_and_rechecks(self):
        # Monitor sees FLAT before the closure reaches OKX history; executor
        # discovers new 10m cooldown. No order is attempted; chain survives.
        now=[0.0]; calls=[]; pauses=[]
        states=iter(("FLAT_ELIGIBLE","COOLDOWN_ACTIVE","FLAT_ELIGIBLE"))
        outcomes=iter(("REENTRY_COOLDOWN_NO_ORDER","NO_CONSENSUS"))
        def fake_run(cmd,timeout):
            calls.append(cmd[2])
            if cmd[2]=="trading.okx_resume_monitor":
                return subprocess.CompletedProcess(cmd,0,
                       "OKX MONITOR RESULT: "+next(states)+"\\n".replace("\\n","\n"),"")
            if cmd[2]=="trading.okx_live_executor":
                return done(cmd,next(outcomes))
            return done(cmd)
        def fake_sleep(seconds):
            pauses.append(seconds); now[0]+=seconds
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES",
                                    "OKX_CAPITAL_MODE":"full_margin"}):
            result=loop(max_cycles=2,resume_after_protected_fill=True,
                        run=fake_run,clock=lambda:now[0],sleep=fake_sleep)
        self.assertEqual(result,0)
        self.assertEqual(calls.count("trading.okx_resume_monitor"),3)
        self.assertEqual(calls.count("trading.six_agent_council"),2)
        self.assertEqual(calls.count("trading.okx_live_executor"),2)
        self.assertEqual(pauses,[30,30])

    def test_no_recurring_opt_in_cannot_accept_cooldown_status(self):
        def fake_run(cmd,timeout):
            if cmd[2]=="trading.okx_live_executor":
                return done(cmd,"REENTRY_COOLDOWN_NO_ORDER")
            return done(cmd)
        self.assertEqual(loop(max_cycles=3,run=fake_run,
                              clock=lambda:0.0),3)

    def test_other_executor_errors_still_stop_without_retries(self):
        calls=[]
        def fake_run(cmd,timeout):
            calls.append(cmd[2])
            if cmd[2]=="trading.okx_resume_monitor":
                return subprocess.CompletedProcess(cmd,0,
                       "OKX MONITOR RESULT: FLAT_ELIGIBLE\n","")
            if cmd[2]=="trading.okx_live_executor":
                return done(cmd,code=2)
            return done(cmd)
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES"}):
            self.assertEqual(loop(resume_after_protected_fill=True,run=fake_run,
                                  clock=lambda:0.0),2)
        self.assertEqual(calls.count("trading.okx_live_executor"),1)

class FullMarginRiskVetoContinueTests(unittest.TestCase):
    def test_risk_veto_continues_monitoring_without_duplicate_order(self):
        seen=[]; pauses=[]; now=[0.]
        outcomes=iter(("RISK_REJECTED_NO_ORDER","NO_CONSENSUS"))
        def run(args,timeout):
            seen.append(args[2])
            if args[2]=="trading.okx_resume_monitor":
                return subprocess.CompletedProcess(args,0,
                    "OKX MONITOR RESULT: FLAT_ELIGIBLE\n","")
            if args[2]=="trading.okx_live_executor":
                return done(args,next(outcomes))
            return done(args)
        def sleep(n):
            pauses.append(n); now[0]+=n
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES",
                                    "OKX_CAPITAL_MODE":"Full_margin"}):
            result=loop(max_cycles=2,run=run,clock=lambda:now[0],
                        sleep=sleep,resume_after_protected_fill=True)
        self.assertEqual(result,0)
        self.assertEqual(seen.count("trading.six_agent_council"),2)
        self.assertEqual(seen.count("trading.okx_live_executor"),2)
        self.assertEqual(seen.count("trading.okx_resume_monitor"),2)
        self.assertEqual(pauses,[5])

    def test_risk_skip_without_separate_repeat_authorization_stops(self):
        def run(args,timeout):
            if args[2]=="trading.okx_live_executor":
                return done(args,"RISK_REJECTED_NO_ORDER")
            return done(args)
        self.assertEqual(loop(max_cycles=3,run=run,
                              clock=lambda:0.),3)

    def test_unknown_block_is_still_fatal_not_risk_skip(self):
        seen=[]
        def run(args,timeout):
            seen.append(args[2])
            if args[2]=="trading.okx_resume_monitor":
                return subprocess.CompletedProcess(args,0,
                    "OKX MONITOR RESULT: FLAT_ELIGIBLE\n","")
            if args[2]=="trading.okx_live_executor":
                return done(args,code=2)
            return done(args)
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES"}):
            self.assertEqual(loop(run=run,clock=lambda:0.,
                                  resume_after_protected_fill=True),2)
        self.assertEqual(seen.count("trading.okx_live_executor"),1)



class CandidateVetoResilienceTests(unittest.TestCase):
    def test_all_explicit_preorder_rejections_are_rescanned(self):
        kinds=("CANDIDATE_REJECTED_NO_ORDER","RISK_REJECTED_NO_ORDER",
               "STALE_SIGNAL_NO_ORDER","NO_CONSENSUS")
        seen=[]; sleeps=[]; now=[0.]
        index=[0]
        def run(cmd,timeout):
            seen.append(cmd[2])
            if cmd[2]=="trading.okx_resume_monitor":
                return subprocess.CompletedProcess(cmd,0,
                     "OKX MONITOR RESULT: FLAT_ELIGIBLE\n","")
            if cmd[2]=="trading.okx_live_executor":
                code=kinds[index[0]]
                index[0]+=1
                return done(cmd,code)
            return done(cmd)
        def sleep(n):sleeps.append(n);now[0]+=n
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES"}):
            self.assertEqual(loop(max_cycles=len(kinds),
                                  resume_after_protected_fill=True,
                                  run=run,clock=lambda:now[0],sleep=sleep),0)
        self.assertEqual(seen.count("trading.six_agent_council"),4)
        self.assertEqual(sleeps,[5,5,5])

    def test_unknown_and_execution_failed_status_never_reenter(self):
        for code,out in ((0,"STRANGE_SUCCESS"),(2,""),(124,"")):
            seen=[]
            def run(cmd,timeout):
                seen.append(cmd[2])
                if cmd[2]=="trading.okx_resume_monitor":
                    return subprocess.CompletedProcess(cmd,0,
                        "OKX MONITOR RESULT: FLAT_ELIGIBLE\n","")
                if cmd[2]=="trading.okx_live_executor":
                    return done(cmd,out or None,code)
                return done(cmd)
            with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES"}):
                result=loop(resume_after_protected_fill=True,run=run,
                            clock=lambda:0.)
            self.assertEqual(result, code if code else 3)
            self.assertEqual(seen.count("trading.okx_live_executor"),1)

    def test_no_opt_in_never_accepts_any_skip_status(self):
        for status in ("CANDIDATE_REJECTED_NO_ORDER","STALE_SIGNAL_NO_ORDER"):
            def run(cmd,timeout):
                return done(cmd,status if cmd[2]=="trading.okx_live_executor" else None)
            self.assertEqual(loop(max_cycles=2,run=run,clock=lambda:0.),3)


class BoundedSessionAndStatusSafetyTests(unittest.TestCase):
    def test_live_bounded_partial_public_scan_cleans_up_for_handoff(self):
        now=[0.0]; calls=[]; timeouts=[]
        def run(args,timeout):
            calls.append(args[2]);timeouts.append(timeout)
            if args[2]=="trading.okx_resume_monitor":
                return subprocess.CompletedProcess(args,0,
                    "OKX MONITOR RESULT: FLAT_ELIGIBLE\n","")
            if args[2]=="trading.six_agent_council":
                if calls.count("trading.six_agent_council")==1:
                    now[0]+=40
                    return done(args)
                # Only the last PUBLIC scan exceeded its remaining bounded
                # window. It has no authority to submit orders.
                self.assertLess(timeout,90)
                now[0]+=timeout
                return done(args,code=124)
            return done(args,"NO_CONSENSUS")
        def sleep(seconds): now[0]+=seconds
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES"}):
            result=loop(max_runtime_seconds=100,run=run,
                        clock=lambda:now[0],sleep=sleep,
                        resume_after_protected_fill=True)
        self.assertEqual(result,0)
        self.assertEqual(calls.count("trading.six_agent_council"),2)
        self.assertEqual(calls.count("trading.okx_live_executor"),1)

    def test_full_public_scan_timeout_remains_fatal(self):
        calls=[]
        def run(args,timeout):
            calls.append((args[2],timeout))
            if args[2]=="trading.okx_resume_monitor":
                return subprocess.CompletedProcess(args,0,
                    "OKX MONITOR RESULT: FLAT_ELIGIBLE\n","")
            return done(args,code=124)
        with patch.dict(os.environ,{"OKX_AUTOREENTRY_ENABLED":"YES"}):
            code=loop(max_runtime_seconds=245,run=run,
                      clock=lambda:0.,resume_after_protected_fill=True)
        self.assertEqual(code,2)
        self.assertEqual(calls[-1],("trading.six_agent_council",90))

    def test_unexpected_success_status_is_explicit_failure_not_silent_stop(self):
        calls=[]
        def run(args,timeout):
            calls.append(args[2])
            return done(args,"UNCLASSIFIED_STATUS") if args[2]=="trading.okx_live_executor" else done(args)
        self.assertEqual(loop(max_cycles=3,run=run,clock=lambda:0.),3)
        self.assertEqual(calls.count("trading.okx_live_executor"),1)
