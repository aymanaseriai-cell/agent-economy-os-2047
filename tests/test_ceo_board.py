import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from automation.ceo_board import (BoardError, blank, execute_board, inbound_candidates,
                                  load_state, main)

NOW = dt.datetime(2026, 11, 21, 6, 30, tzinfo=dt.timezone.utc)
URL = "https://github.com/example/coding/issues/39"
SELF_URL = "https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/122"


def decision(*shortlist):
    return {"schema": "agent-economy-ceo-decision/1", "generated_at": "2026-11-21T06:29:00Z",
            "health": "ok", "top_manual_review": list(shortlist)}


def research(url=URL, score=18):
    return {"url": url, "heuristic_score": score, "buyer_verified": False, "contact_allowed": False}


def inbound(author="external-user", url=SELF_URL, title="[Service request] Evidence acceptance", body="### What service do you want?\n\nEvaluate agent handoff evidence and buyer acceptance"):
    return {"html_url": url, "state": "open", "user": {"login": author}, "title": title,
            "body": body}


class CEOBoardTests(unittest.TestCase):
    def test_empty_board(self):
        _, r = execute_board(decision(), blank(), [], NOW)
        self.assertIsNone(r["decision"])
        self.assertFalse(r["outbound_communication_authorized"])

    def test_external_service_request_priority(self):
        _, r = execute_board(decision(research()), blank(), [inbound()], NOW)
        self.assertEqual(r["decision"]["url"], SELF_URL)
        self.assertEqual(r["decision"]["hypothesis"], "h2")
        self.assertFalse(r["decision"]["verified_buyer"])
        self.assertIsNone(r["verified_paid_customers"])

    def test_owner_issue_not_external(self):
        _, r = execute_board(decision(), blank(), [inbound(author="aymanaseriai-cell")], NOW)
        self.assertIsNone(r["decision"])

    def test_bot_request_not_independent(self):
        _, r = execute_board(decision(), blank(), [inbound(author="github-actions[bot]")], NOW)
        self.assertIsNone(r["decision"])

    def test_unrelated_issue_ignored(self):
        _, r = execute_board(decision(), blank(), [inbound(title="Bug: build failed")], NOW)
        self.assertIsNone(r["decision"])

    def test_forked_issue_url_rejected(self):
        _, r = execute_board(decision(), blank(), [inbound(url=URL)], NOW)
        self.assertIsNone(r["decision"])

    def test_issue_closed_ignored(self):
        x=inbound();x["state"]="closed"
        _, r=execute_board(decision(),blank(),[x],NOW)
        self.assertIsNone(r["decision"])

    def test_pulls_are_not_inbound_service(self):
        x=inbound();x["pull_request"]={"url":"foo"}
        _,r=execute_board(decision(),blank(),[x],NOW)
        self.assertIsNone(r["decision"])

    def test_research_never_authorizes_contact(self):
        _, r = execute_board(decision(research()), blank(), [], NOW)
        self.assertFalse(r["decision"]["contact_allowed"])
        self.assertFalse(r["outbound_communication_authorized"])
        self.assertIsNone(r["verified_revenue_usd"])

    def test_fake_research_budget_rejected(self):
        x=research();x["buyer_verified"]=True
        with self.assertRaisesRegex(BoardError,"UNSUPPORTED_RESEARCH_CLAIM"):
            execute_board(decision(x), blank(), [], NOW)

    def test_no_duplicate_jobs_hourly(self):
        a, r = execute_board(decision(research()), blank(), [], NOW)
        b, s = execute_board(decision(research()), a, [], NOW + dt.timedelta(minutes=5))
        self.assertTrue(r["queued_this_run"])
        self.assertFalse(s["queued_this_run"])
        self.assertEqual(b["jobs"], a["jobs"])

    def test_pending_job_is_not_claimed_completed(self):
        a, _=execute_board(decision(research()),blank(),[],NOW)
        _, r=execute_board(decision(research()),a,[],NOW+dt.timedelta(minutes=5))
        self.assertEqual(r["decision"]["reason"],"Previously queued; not yet executed.")
        self.assertFalse(r["executed_external_action"])

    def test_manual_review_requires_evidence_link(self):
        a,_=execute_board(decision(research()),blank(),[],NOW)
        a["jobs"][URL]["status"]="reviewed"
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"state.json";p.write_text(json.dumps(a))
            with self.assertRaisesRegex(BoardError,"MISSING_REVIEW_EVIDENCE"):
                load_state(p)

    def test_reviewed_job_with_evidence_proceeds_to_next(self):
        a,_=execute_board(decision(research()),blank(),[],NOW)
        a["jobs"][URL]["status"]="rejected"
        a["jobs"][URL]["evidence_url"]="https://github.com/example/coding/issues/39"
        other="https://github.com/example/coding/issues/40"
        b,r=execute_board(decision(research(),research(other,19)),a,[],NOW+dt.timedelta(minutes=5))
        self.assertTrue(r["queued_this_run"])
        self.assertEqual(r["decision"]["url"],other)
        self.assertEqual(len(b["jobs"]),2)

    def test_no_conflicting_experiment_payout(self):
        a,r=execute_board(decision(research()),blank(),[],NOW)
        self.assertFalse(r["outbound_communication_authorized"])
        self.assertIsNone(r["verified_paid_customers"])

    def test_partial_github_fetch_reported(self):
        _,r=execute_board(decision(research()),blank(),[],NOW,"inbound_fetch_failed")
        self.assertEqual(r["health"],"partial_data")

    def test_stale_radar_refused(self):
        with self.assertRaisesRegex(BoardError,"STALE_RESEARCH"):
            execute_board(decision(research()),blank(),[],NOW+dt.timedelta(hours=5))

    def test_malformed_persisted_state_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"strategy.json";p.write_text('{"schema":"wrong"}')
            with self.assertRaisesRegex(BoardError,"BAD_BOARD_STATE"):
                load_state(p)

    def test_cli_read_existing_state_and_inbound_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); source=base/"decision.json"; state=base/"strategy.json"; incoming=base/"inbound.json"; out=base/"warroom.json"
            source.write_text(json.dumps(decision(research())))
            incoming.write_text(json.dumps([inbound()]))
            argv=["--decision",str(source),"--state",str(state),"--inbound",str(incoming),"--out",str(out),"--now",NOW.isoformat()]
            self.assertEqual(main(argv),0)
            self.assertEqual(json.loads(out.read_text())["decision"]["url"],SELF_URL)
            self.assertEqual(main(argv),0)
            self.assertEqual(len(json.loads(state.read_text())["jobs"]),1)

    def test_reject_missing_evidence_on_completed(self):
        a,_=execute_board(decision(research()),blank(),[],NOW)
        a["jobs"][URL]["status"]="completed"
        a["jobs"][URL]["evidence_url"]="https://github.com/example/coding/issues/39"
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"s.json";p.write_text(json.dumps(a))
            with self.assertRaisesRegex(BoardError,"MISSING_COMPLETION_EFFECT"):
                load_state(p)

    def test_opt_in_challenge_still_not_buyer(self):
        x=inbound(title="[Evidence challenge] test")
        _, r=execute_board(decision(),blank(),[x],NOW)
        self.assertEqual(r["decision"]["priority"],60)
        self.assertFalse(r["decision"]["contact_allowed"])


if __name__ == "__main__":
    unittest.main()
