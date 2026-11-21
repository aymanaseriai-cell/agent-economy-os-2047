import json
import tempfile
import unittest
from pathlib import Path
from automation.factory_operator import plan_dispatch, execute_reviewonly, PREFIX, ALLOWED_ACTION
from automation.worker_dispatcher import PolicyError
from automation.worker_fleet import REGISTRY

def item(w, status="QUEUED", priority=2, **updates):
    row = {"work_key": PREFIX+w, "owner_role": REGISTRY[w].owner_role,
           "action_code": ALLOWED_ACTION[w], "priority": priority,
           "work_status": status, "proof_ref": None}
    row.update(updates)
    return row

class FactoryOperatorTests(unittest.TestCase):
    def test_four_executives_select_from_role_owned_queue(self):
        p=plan_dispatch([item("AEOS-W01"), item("AEOS-W02",priority=1),
                         item("AEOS-W06","NEEDS_APPROVAL",1),
                         item("AEOS-W07","BLOCKED",1),
                         item("AEOS-W12","BLOCKED",1)])
        self.assertEqual([x["executive"] for x in p["selected"]],
                         ["CEO","CTO","CRO","COO_CFO"])
        self.assertEqual(p["selected"][0]["worker_id"],"AEOS-W02")
        self.assertEqual(p["selected"][1]["disposition"],"ESCALATE_INDEPENDENT_APPROVAL")
        self.assertEqual(p["selected"][2]["disposition"],"WAIT_EXTERNAL_EVIDENCE")
        self.assertEqual(p["independent_llm_sessions"],0)

    def test_real_verified_work_skipped_without_new_signal(self):
        p=plan_dispatch([item("AEOS-W04","VERIFIED",proof_ref="https://github.com/one")])
        self.assertEqual(p["selected"][1]["disposition"],"NO_NEW_EVIDENCE")
        self.assertIsNone(p["selected"][1]["worker_id"])

    def test_queued_bounded_worker_over_blocked(self):
        p=plan_dispatch([item("AEOS-W03"),item("AEOS-W06","NEEDS_APPROVAL",1)])
        self.assertEqual(p["selected"][1]["worker_id"],"AEOS-W03")

    def test_duplicate_worker_rejected(self):
        with self.assertRaises(PolicyError): plan_dispatch([item("AEOS-W02"),item("AEOS-W02")])

    def test_unknown_worker_rejected(self):
        with self.assertRaises(PolicyError): plan_dispatch([item("AEOS-W01", work_key=PREFIX+"AEOS-W99")])

    def test_foreign_work_key_rejected(self):
        with self.assertRaises(PolicyError): plan_dispatch([item("AEOS-W01",work_key="evil:AEOS-W01")])

    def test_wrong_executive_rejected(self):
        with self.assertRaises(PolicyError): plan_dispatch([item("AEOS-W03",owner_role="CRO")])

    def test_tool_escalation_rejected(self):
        with self.assertRaises(PolicyError): plan_dispatch([item("AEOS-W11",action_code="TRANSFER_FUNDS")])

    def test_invalid_priority_rejected(self):
        for n in (True,0,9,"1",None):
            with self.subTest(n=n),self.assertRaises(PolicyError):
                plan_dispatch([item("AEOS-W01",priority=n)])

    def test_verified_without_proof_rejected(self):
        with self.assertRaises(PolicyError): plan_dispatch([item("AEOS-W01","VERIFIED")])

    def test_illegal_status_rejected(self):
        with self.assertRaises(PolicyError): plan_dispatch([item("AEOS-W04","PAID")])

    def test_more_than_twelve_rejected(self):
        with self.assertRaises(PolicyError): plan_dispatch([item("AEOS-W01")]*13)

    def test_no_eligible_skips_all_external_execution(self):
        p=plan_dispatch([item("AEOS-W06","NEEDS_APPROVAL",1)])
        r=execute_reviewonly(p,[],Path("."))
        self.assertEqual(r["dispatched_count"],0)
        self.assertFalse(r["production_changes"])

    def test_real_selected_local_digest_worker_runs_without_write(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,"verifier.py").write_text("print('safe')",encoding="utf-8")
            p=plan_dispatch([item("AEOS-W03")])
            r=execute_reviewonly(p,[{"worker_id":"AEOS-W03","payload":{"path":"verifier.py"}}],Path(d))
            self.assertEqual(r["dispatched_count"],1)
            self.assertEqual(r["technically_verified_readonly_count"],1)
            self.assertFalse(r["receipts"][0]["production_change"])
            self.assertFalse(r["receipts"][0]["model_agent_instantiated"])

    def test_forged_manager_selection_rejected(self):
        p=plan_dispatch([item("AEOS-W03")])
        p["selected"][1]["worker_id"]="AEOS-W09"
        with self.assertRaises(PolicyError):
            execute_reviewonly(p,[],Path("."))

    def test_forged_action_rejected(self):
        p=plan_dispatch([item("AEOS-W03")])
        p["selected"][1]["action_code"]="TRANSFER_FUNDS"
        with self.assertRaises(PolicyError):
            execute_reviewonly(p,[],Path("."))

    def test_ineligible_worker_cannot_be_smuggled_into_execution(self):
        p=plan_dispatch([item("AEOS-W03")])
        with self.assertRaises(PolicyError):
            execute_reviewonly(p,[{"worker_id":"AEOS-W04","payload":{}}],Path("."))

    def test_active_work_preempts_new_queued_worker_with_higher_priority(self):
        p=plan_dispatch([item("AEOS-W03","IN_PROGRESS",priority=5),
                         item("AEOS-W04","QUEUED",priority=1)])
        selected=p["selected"][1]
        self.assertEqual(selected["worker_id"],"AEOS-W03")
        self.assertEqual(selected["disposition"],"VERIFY_IN_PROGRESS_FIRST")
        with tempfile.TemporaryDirectory() as d:
            Path(d, "verifier.py").write_text("print('safe')", encoding="utf-8")
            jobs=[{"worker_id":"AEOS-W03", "payload":{"path":"verifier.py"}}]
            result=execute_reviewonly(p,jobs,Path(d))
            self.assertEqual(result["dispatched_count"],1)
            self.assertEqual(result["rechecked_in_progress_count"],1)
            self.assertEqual(result["technically_verified_readonly_count"],1)
            self.assertEqual([r["worker_id"] for r in result["receipts"]], ["AEOS-W03"])
            self.assertFalse(result["production_changes"])

    def test_cli_invalid_json_fails_closed_with_stderr_and_no_output(self):
        import io
        from contextlib import redirect_stderr
        from automation import factory_operator
        with tempfile.TemporaryDirectory() as d:
            orders = Path(d) / "invalid.json"
            output = Path(d) / "result.json"
            orders.write_text("{invalid-json", encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = factory_operator.main(
                    ["--orders", str(orders), "--out", str(output)])
            self.assertEqual(exit_code, 2)
            self.assertIn("FACTORY_FAIL_CLOSED: JSONDecodeError", err.getvalue())
            self.assertFalse(output.exists())

    def test_interrupted_in_progress_probe_requires_exact_allowlisted_job(self):
        p=plan_dispatch([item("AEOS-W03","IN_PROGRESS")])
        with self.assertRaisesRegex(PolicyError, "MISSING_EXACT_SELECTED_JOB"):
            execute_reviewonly(p,[],Path("."))
        with self.assertRaises(PolicyError):
            execute_reviewonly(p,[{"worker_id":"AEOS-W04","payload":{}}],Path("."))

    def test_forged_approval_cannot_be_promoted_to_execution(self):
        p=plan_dispatch([item("AEOS-W06","NEEDS_APPROVAL",priority=1)])
        p["selected"][1]["disposition"]="REVIEW_ONLY_ACTION_ELIGIBLE"
        with self.assertRaisesRegex(PolicyError,"PLAN_STATUS_DISPOSITION_MISMATCH"):
            execute_reviewonly(p,[{"worker_id":"AEOS-W06","payload":{"issue_number":98}}],Path("."))

    def test_forged_work_key_cannot_route_other_reviewonly_worker(self):
        p=plan_dispatch([item("AEOS-W03")])
        p["selected"][1]["work_key"]=PREFIX+"AEOS-W04"
        with self.assertRaisesRegex(PolicyError,"FORGED_ACTION_SELECTION"):
            execute_reviewonly(p,[{"worker_id":"AEOS-W03","payload":{"path":"verifier.py"}}],Path("."))

if __name__=="__main__":
    unittest.main()
