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

    def test_auto_discovery_isolates_provider_failure_and_skips_blocked(self):
        from automation.factory_cycle import run_live_review_cycle
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "verifier.py").write_text("fixture", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "ENTERPRISE_EVIDENCE_PILOT.md").write_text("fixture", encoding="utf-8")
            orders = [item("AEOS-W04", "IN_PROGRESS"), item("AEOS-W03"),
                      item("AEOS-W09"), item("AEOS-W06", "NEEDS_APPROVAL")]
            calls = []
            def discover(fetch, *, selected_workers):
                w = selected_workers[0]
                calls.append(w)
                if w == "AEOS-W04":
                    raise OSError("CI unavailable")
                return {"jobs": [{"worker_id": w}]}
            with patch("automation.worker_fleet_live.prepare_live_jobs", side_effect=discover):
                result = run_live_review_cycle(orders, root)
            self.assertEqual(calls, ["AEOS-W04", "AEOS-W03", "AEOS-W09"])
            self.assertEqual(result["cycle_status"], "DEGRADED")
            self.assertEqual(result["discovery_blocked_worker_ids"], ["AEOS-W04"])
            self.assertEqual(result["technically_verified_readonly_count"], 2)
            self.assertEqual(result["business_deliveries_verified"], 0)
            self.assertFalse(result["production_release_authorized"])

    def test_auto_discovery_rejects_foreign_worker_before_execution(self):
        from automation.factory_cycle import run_live_review_cycle
        from unittest.mock import patch
        with (patch("automation.worker_fleet_live.prepare_live_jobs",
                    return_value={"jobs": [{"worker_id": "AEOS-W09"}]}),
              patch("automation.factory_cycle.run_review_cycle") as run):
            with self.assertRaisesRegex(PolicyError, "CYCLE_DISCOVERY_WORKER_MISMATCH"):
                run_live_review_cycle([item("AEOS-W03")], Path("."))
            run.assert_not_called()

    def test_auto_discovery_validates_all_orders_first(self):
        from automation.factory_cycle import run_live_review_cycle
        from unittest.mock import patch
        with patch("automation.worker_fleet_live.prepare_live_jobs") as discover:
            with self.assertRaises(PolicyError):
                run_live_review_cycle([item("AEOS-W03"), item("AEOS-W09", owner_role="CTO")], Path("."))
            discover.assert_not_called()

    def test_auto_discovery_cli_records_degraded_report(self):
        from automation.factory_cycle import main
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inp, out = root / "orders.json", root / "result.json"
            inp.write_text(json.dumps([item("AEOS-W04")]), encoding="utf-8")
            with patch("automation.worker_fleet_live.prepare_live_jobs", side_effect=OSError("offline")):
                code = main(["--orders", str(inp), "--auto-live-jobs", "--root", str(root), "--out", str(out)])
            self.assertEqual(code, 2)
            result = json.loads(out.read_text())
            self.assertEqual(result["discovery_blocked_worker_ids"], ["AEOS-W04"])
            self.assertEqual(result["dispatched_count"], 0)
            self.assertFalse(result["persistent_scheduler_installed"])

    def test_checkpoint_retains_first_round_when_later_round_fails(self):
        from automation import factory_cycle
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            for filename in ("docs/ENTERPRISE_EVIDENCE_PILOT.md", "buyer-gate/README.md"):
                p = root / filename
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("fixture", encoding="utf-8")
            inp, jobs, out, journal = [root / n for n in ("orders.json","jobs.json","out.json","journal.json")]
            inp.write_text(json.dumps([item("AEOS-W09"), item("AEOS-W10", priority=3)]))
            jobs.write_text(json.dumps([{"worker_id": "AEOS-W09"}, {"worker_id": "AEOS-W10"}]))
            original = factory_cycle.execute_reviewonly
            calls = []
            def interrupt(*args, **kwargs):
                calls.append(1)
                if len(calls) == 2:
                    raise OSError("interrupted")
                return original(*args, **kwargs)
            with patch("automation.factory_cycle.execute_reviewonly", side_effect=interrupt):
                rc = factory_cycle.main(["--orders",str(inp),"--jobs",str(jobs),
                    "--out",str(out),"--root",str(root),"--checkpoint",str(journal)])
            self.assertEqual(rc, 2)
            self.assertFalse(out.exists())
            record = json.loads(journal.read_text())
            self.assertEqual(record["state"], "FAILED_INCOMPLETE")
            self.assertEqual(record["progress"]["rounds_completed"], 1)
            self.assertEqual(len(record["progress"]["receipts"]), 1)
            self.assertFalse(record["production_release_authorized"])

    def test_checkpoint_cannot_overwrite_inputs_or_previous_journal(self):
        from automation.factory_cycle import main
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inp, jobs, out, journal = [root / n for n in ("orders.json","jobs.json","out.json","journal.json")]
            inp.write_text("[]")
            jobs.write_text("[]")
            journal.write_text("previous evidence")
            args = ["--orders",str(inp),"--jobs",str(jobs),"--out",str(out)]
            self.assertEqual(main(args+["--checkpoint",str(inp)]), 2)
            self.assertEqual(inp.read_text(), "[]")
            self.assertEqual(main(args+["--checkpoint",str(journal)]), 2)
            self.assertEqual(journal.read_text(), "previous evidence")
            self.assertFalse(out.exists())

    def test_completed_journal_binds_final_report_to_run(self):
        from automation.factory_cycle import main
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inp, jobs, out, journal = [root / n for n in ("orders.json","jobs.json","out.json","journal.json")]
            inp.write_text("[]")
            jobs.write_text("[]")
            rc = main(["--orders",str(inp),"--jobs",str(jobs),"--out",str(out),
                       "--checkpoint",str(journal)])
            self.assertEqual(rc, 0)
            a, b = json.loads(out.read_text()), json.loads(journal.read_text())
            self.assertEqual(a["run_id"], b["run_id"])
            self.assertEqual(b["state"], "FINAL_REPORT_WRITTEN")
            self.assertEqual(b["progress"]["receipts"], [])
            self.assertFalse(a["persistent_scheduler_installed"])

    def test_recovery_skips_historical_verified_without_counting_new_receipt(self):
        from automation import factory_cycle
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            orders = [item("AEOS-W09"), item("AEOS-W10", priority=3)]
            for w in ("AEOS-W09", "AEOS-W10"):
                p = root / REGISTRY[w].default_payload["path"]
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("fixture")
            jobs = [{"worker_id": w} for w in ("AEOS-W09", "AEOS-W10")]
            inp, j, first, checkpoint, second, next_checkpoint = [
                root / n for n in ("orders.json","jobs.json","first.json",
                                   "checkpoint.json","second.json","next.json")]
            inp.write_text(json.dumps(orders))
            j.write_text(json.dumps(jobs))
            original = factory_cycle.execute_reviewonly
            calls = []
            def fail_second(*args, **kwargs):
                calls.append(1)
                if len(calls) == 2:
                    raise OSError("interrupted")
                return original(*args, **kwargs)
            base = ["--orders", str(inp), "--jobs", str(j), "--root", str(root)]
            with patch("automation.factory_cycle.execute_reviewonly", side_effect=fail_second):
                self.assertEqual(factory_cycle.main(base + ["--out", str(first),
                                 "--checkpoint", str(checkpoint)]), 2)
            before = checkpoint.read_bytes()
            rc = factory_cycle.main(base + ["--out", str(second), "--checkpoint",
                                    str(next_checkpoint), "--resume-from", str(checkpoint)])
            self.assertEqual(rc, 0)
            report = json.loads(second.read_text())
            self.assertEqual(report["recovery"]["historical_worker_ids_not_reverified"], ["AEOS-W09"])
            self.assertEqual([r["worker_id"] for r in report["receipts"]], ["AEOS-W10"])
            self.assertEqual(report["technically_verified_readonly_count"], 1)
            self.assertFalse(report["full_original_snapshot_freshly_verified"])
            self.assertFalse(report["production_release_authorized"])
            self.assertEqual(checkpoint.read_bytes(), before)
            self.assertEqual(report["business_deliveries_verified"], 0)
            changed = [item("AEOS-W09", priority=1), item("AEOS-W10", priority=3)]
            with self.assertRaisesRegex(PolicyError, "RECOVERY_SNAPSHOT_MISMATCH"):
                factory_cycle.recovery_orders(changed, json.loads(before))
            tampered = json.loads(before)
            tampered["progress"]["decisions"][0]["action_code"] = "TRANSFER_FUNDS"
            with self.assertRaisesRegex(PolicyError, "RECOVERY_DECISION_MISMATCH"):
                factory_cycle.recovery_orders(orders, tampered)
            tampered = json.loads(before)
            tampered["progress"]["receipts"] = []
            with self.assertRaisesRegex(PolicyError, "RECOVERY_RECEIPT_SET_MISMATCH"):
                factory_cycle.recovery_orders(orders, tampered)

    def test_recovery_never_accepts_completed_journal_or_missing_progress(self):
        from automation.factory_cycle import recovery_orders
        j = {"schema": "aeos2047-review-cycle-journal/1", "state": "FINAL_REPORT_WRITTEN",
             "run_id": "a"*32, "production_release_authorized": False,
             "business_deliveries_verified": 0, "verified_revenue_usd": None}
        with self.assertRaisesRegex(PolicyError, "INVALID_OR_ALREADY_RESUMED_JOURNAL"):
            recovery_orders([], j)
        j["state"] = "IN_PROGRESS"
        with self.assertRaisesRegex(PolicyError, "RECOVERY_SNAPSHOT_MISMATCH"):
            recovery_orders([], j)
