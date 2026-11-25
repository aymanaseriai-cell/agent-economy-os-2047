import json
import tempfile
import unittest
from pathlib import Path
from automation.factory_operator import PREFIX, ALLOWED_ACTION
from automation.worker_dispatcher import PolicyError
from automation.worker_fleet import REGISTRY

def item(w, status="QUEUED", priority=2, **updates):
    row = {"work_key":PREFIX+w, "owner_role":REGISTRY[w].owner_role,
           "action_code":ALLOWED_ACTION[w], "priority":priority,
           "work_status":status, "proof_ref":None}
    row.update(updates)
    return row

class FactoryCycleTests(unittest.TestCase):
    def test_cycle_drains_later_workers_after_missing_evidence(self):
        from automation.factory_cycle import run_review_cycle
        orders = [item("AEOS-W04","IN_PROGRESS",5), item("AEOS-W03",priority=1),
                  item("AEOS-W09",priority=1), item("AEOS-W10",priority=2),
                  item("AEOS-W06","NEEDS_APPROVAL"), item("AEOS-W12","BLOCKED")]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for w in ("AEOS-W03","AEOS-W09","AEOS-W10"):
                p = root / REGISTRY[w].default_payload["path"]
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("fixture", encoding="utf-8")
            jobs = [{"worker_id":w} for w in ("AEOS-W03","AEOS-W09","AEOS-W10")]
            before = json.dumps(orders,sort_keys=True)
            result = run_review_cycle(orders,jobs,root)
            self.assertEqual(json.dumps(orders,sort_keys=True),before)
        results = {x["worker_id"]:x["cycle_result"] for x in result["decisions"]}
        self.assertEqual(results["AEOS-W04"],"BLOCKED_MISSING_JOB_EVIDENCE")
        self.assertEqual(results["AEOS-W03"],"TECHNICAL_READONLY_VERIFIED")
        self.assertEqual(results["AEOS-W06"],"ESCALATE_INDEPENDENT_APPROVAL")
        self.assertEqual(results["AEOS-W12"],"WAIT_EXTERNAL_EVIDENCE")
        self.assertEqual(result["technically_verified_readonly_count"],3)
        self.assertEqual(result["dispatched_count"],3)
        self.assertEqual(result["business_deliveries_verified"],0)
        self.assertFalse(result["production_release_authorized"])
        self.assertIsNone(result["verified_revenue_usd"])

    def test_cycle_does_not_repeat_verified_or_duplicate_workers(self):
        from automation.factory_cycle import run_review_cycle
        orders = [item("AEOS-W03","VERIFIED",proof_ref="https://github.com/one")]
        result = run_review_cycle(orders,[{"worker_id":"AEOS-W03"}],Path("."))
        self.assertEqual(result["dispatched_count"],0)
        self.assertEqual(result["previously_verified_not_reexecuted"],1)
        with self.assertRaisesRegex(PolicyError,"DUPLICATE_LIVE_JOB"):
            run_review_cycle(orders,[{"worker_id":"AEOS-W03"}]*2,Path("."))

    def test_cycle_rejects_scope_escalation_before_dispatch(self):
        from automation.factory_cycle import run_review_cycle
        from unittest.mock import patch
        with patch("automation.factory_cycle.execute_reviewonly") as fleet:
            with self.assertRaises(PolicyError):
                run_review_cycle([item("AEOS-W03")],
                                 [{"worker_id":"AEOS-W03","payload":{"path":"secret.txt"}}],
                                 Path("."))
            fleet.assert_not_called()


