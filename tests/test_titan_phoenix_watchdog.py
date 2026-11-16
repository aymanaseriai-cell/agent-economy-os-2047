import copy
import unittest
from trading.titan_phoenix_watchdog import decide, EXPECTED_JOB_STEPS, WORKFLOW_PATH

NOW=1790000000000

def healthy():
    end="2026-09-17T08:00:00Z"
    # Avoid depending on wall clock, choose exact epoch in both fields.
    from datetime import datetime,timezone
    end=datetime.fromtimestamp((NOW-15*60000)/1000,timezone.utc).isoformat()
    start=datetime.fromtimestamp((NOW-19*60000)/1000,timezone.utc).isoformat()
    return {"flags":{"OKX_STOP_CONTINUOUS":"NO",
                      "OKX_ENABLE_REAL_TRADING":"YES",
                      "OKX_EXECUTION_MODE":"live",
                      "OKX_PHOENIX_RESUME_ARM":"YES"},
            "workflow_state":"active",
            "runs":[{"id":111,"path":WORKFLOW_PATH,"event":"workflow_dispatch",
                     "head_branch":"main","status":"completed",
                     "conclusion":"success","created_at":start,
                     "updated_at":end}],
            "last_run_jobs":[{"status":"completed","conclusion":"success",
                              "steps":[{"name":s,"conclusion":"success"}
                                       for s in EXPECTED_JOB_STEPS]}]}

class PhoenixTests(unittest.TestCase):
    def test_clean_previous_continuous_session_can_recover(self):
        x=decide(healthy(),now_ms=NOW)
        self.assertEqual(x["action"],"RESUME_CLEAN_SESSION")
        self.assertEqual(x["last_run_id"],111)
        self.assertFalse(x["auto_repairs_code"])

    def test_owner_stop_dominates_everything(self):
        x=healthy()
        x["flags"]["OKX_STOP_CONTINUOUS"]="YES"
        self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")

    def test_live_disabled_dominates(self):
        x=healthy()
        x["flags"]["OKX_ENABLE_REAL_TRADING"]="NO"
        self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")

    def test_separate_phoenix_arm_mandatory(self):
        x=healthy()
        del x["flags"]["OKX_PHOENIX_RESUME_ARM"]
        self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")

    def test_disabled_live_workflow(self):
        x=healthy()
        x["workflow_state"]="disabled_manually"
        self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")

    def test_existing_active_run_blocks_duplicates(self):
        x=healthy()
        x["runs"].append(dict(x["runs"][0],id=222,status="in_progress",
                              conclusion=None))
        self.assertEqual(decide(x,now_ms=NOW)["action"],"WAIT")

    def test_clean_last_run_under_nine_minutes_wait(self):
        x=healthy()
        self.assertEqual(decide(x,now_ms=NOW-10*60000)["action"],"WAIT")

    def test_no_recent_session_requires_manual_authorization(self):
        x=healthy()
        self.assertEqual(decide(x,now_ms=NOW+2*3600000)["action"],"STOP")

    def test_failed_and_cancelled_runs_never_auto_restarted(self):
        for status in ("failure","cancelled","timed_out","action_required"):
            with self.subTest(status=status):
                x=healthy()
                x["runs"][0]["conclusion"]=status
                self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")

    def test_missing_chain_step_blocks_restart(self):
        for step in EXPECTED_JOB_STEPS:
            with self.subTest(step=step):
                x=healthy()
                x["last_run_jobs"][0]["steps"]=[
                    s for s in x["last_run_jobs"][0]["steps"] if s["name"]!=step]
                self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")

    def test_skipped_chain_step_blocks_restart(self):
        x=healthy()
        x["last_run_jobs"][0]["steps"][-1]["conclusion"]="skipped"
        self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")

    def test_unknown_manual_validate_session_blocks_restart(self):
        x=healthy()
        x["last_run_jobs"][0]["steps"]=[]
        self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")

    def test_research_and_branch_runs_block(self):
        x=healthy();x["runs"][0]["head_branch"]="experimental"
        self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")
        x=healthy();x["runs"][0]["event"]="schedule"
        self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")

    def test_absent_jobs_or_runs_do_not_recover(self):
        x=healthy();x["last_run_jobs"]=[]
        self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")
        x=healthy();x["runs"]=[]
        self.assertEqual(decide(x,now_ms=NOW)["action"],"STOP")

    def test_never_trade_from_classifier(self):
        import inspect, trading.titan_phoenix_watchdog as m
        source=inspect.getsource(m)
        for forbidden in ("OKX_API_KEY", "OKX_SECRET_KEY",
                          "/api/v5/trade/order", "place_order(",
                          "subprocess.run(","requests.post("):
            self.assertNotIn(forbidden,source)
        self.assertEqual(decide(healthy(),now_ms=NOW)["order_count"],0)

if __name__=="__main__":
    unittest.main()
