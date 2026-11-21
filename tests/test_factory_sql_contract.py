"""Enforce parity of review-only SQL and Python executive factory priority."""
import re
import unittest
from pathlib import Path
from automation.factory_operator import plan_dispatch, PREFIX, ALLOWED_ACTION
from automation.worker_fleet import REGISTRY

SOURCE = Path(__file__).resolve().parents[1] / "infra/supabase/factory_reviewonly_router_20261121.sql"

def order(worker, state, priority):
    return {"work_key":PREFIX+worker, "owner_role":REGISTRY[worker].owner_role,
            "action_code":ALLOWED_ACTION[worker], "work_status":state,
            "priority":priority, "proof_ref":None}

class FactorySqlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = SOURCE.read_text(encoding="utf-8")

    def test_sql_selects_in_progress_before_queued(self):
        m = re.search(
            r"ORDER BY CASE work_status WHEN 'IN_PROGRESS' THEN (\\d+) WHEN 'QUEUED' THEN (\\d+)\\s+WHEN 'NEEDS_APPROVAL' THEN (\\d+) ELSE (\\d+) END",
            self.sql.replace("\\n", " ")
        )
        self.assertIsNotNone(m, "SQL factory priority order drifted")
        self.assertEqual(tuple(map(int, m.groups())), (1,2,3,4))

    def test_python_reconciles_in_progress_even_if_queued_is_priority_one(self):
        plan=plan_dispatch([order("AEOS-W03","IN_PROGRESS",5),
                            order("AEOS-W04","QUEUED",1)])
        cto=plan["selected"][1]
        self.assertEqual(cto["worker_id"],"AEOS-W03")
        self.assertEqual(cto["disposition"],"VERIFY_IN_PROGRESS_FIRST")

    def test_release_boundary_not_bypassed(self):
        self.assertIn("REVIEW-ONLY CORRECTION (not yet deployed)",self.sql)
        self.assertIn("REVOKE ALL ON FUNCTION executive_nexus.run_factory_review_cycle()",self.sql)
        self.assertIn("'actual_worker_actions',0",self.sql)
        self.assertIn("'production_changes',0",self.sql)
        self.assertIn("'external_contacts',0",self.sql)
if __name__=="__main__":
    unittest.main()
