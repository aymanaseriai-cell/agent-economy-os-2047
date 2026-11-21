import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from automation.ceo_memory import new_state, read_state, reconcile, run


NOW = dt.datetime(2026, 11, 21, 5, 55, tzinfo=dt.timezone.utc)
URL = "https://github.com/realteam/agent-work/issues/23"


def radar(*issues):
    return {
        "schema_version": "agent-economy-public-demand-radar/2.0",
        "generated_at": "2026-11-21T05:54:00Z",
        "candidate_issues": list(issues),
        "errors": [],
    }


def candidate(url=URL, score=17, tier="manual_buyer_intent_review"):
    return {"url": url, "score": score, "tier": tier, "buyer_intent_verified": False,
            "funded_opportunity_verified": False}


class CEOMemoryTests(unittest.TestCase):
    def test_empty_ledger(self):
        s, x = reconcile(radar(), new_state(), NOW)
        self.assertEqual(x["remembered_candidates"], 0)
        self.assertIsNone(x["next_issue_url"])

    def test_first_detection_is_not_verified_buyer(self):
        s, x = reconcile(radar(candidate()), new_state(), NOW)
        self.assertEqual(x["new_research_candidates"], 1)
        self.assertFalse(x["approval_to_contact"])
        self.assertEqual(x["verified_buyers"], 0)
        self.assertIsNone(x["verified_revenue_usd"])

    def test_no_double_count_for_same_day(self):
        s, _ = reconcile(radar(candidate()), new_state(), NOW)
        t, x = reconcile(radar(candidate()), s, NOW + dt.timedelta(minutes=5))
        self.assertEqual(x["new_research_candidates"], 0)
        self.assertEqual(t["seen"][URL]["days_observed"], 1)

    def test_next_day_observation_and_retention(self):
        s, _ = reconcile(radar(candidate()), new_state(), NOW)
        rr = radar(candidate());rr["generated_at"]="2026-11-22T05:53:00Z"
        t, _ = reconcile(rr, s, NOW+dt.timedelta(days=1))
        self.assertEqual(t["seen"][URL]["days_observed"], 2)

    def test_suppressed_candidate_not_reconsidered(self):
        prev=new_state()
        prev["reviews"][URL]="suppressed"
        t,x=reconcile(radar(candidate()),prev,NOW)
        self.assertEqual(x["remembered_candidates"],0)
        self.assertEqual(x["suppressed_or_unusable"],1)

    def test_url_defensive_check(self):
        t,x=reconcile(radar(candidate("https://evil.org/call")),new_state(),NOW)
        self.assertEqual(x["remembered_candidates"],0)

    def test_self_issue_not_external_buyer(self):
        t,x=reconcile(radar(candidate("https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/1")),new_state(),NOW)
        self.assertEqual(x["remembered_candidates"],0)

    def test_stale_radar_rejected(self):
        with self.assertRaisesRegex(ValueError,"RADAR_NOT_CURRENT"):
            reconcile(radar(candidate()),new_state(),NOW+dt.timedelta(hours=5))

    def test_future_radar_rejected(self):
        with self.assertRaisesRegex(ValueError,"RADAR_NOT_CURRENT"):
            reconcile(radar(candidate()),new_state(),NOW-dt.timedelta(minutes=8))

    def test_false_verified_claim_rejected(self):
        c=candidate();c["buyer_intent_verified"]=True
        with self.assertRaisesRegex(ValueError,"RADAR_CLAIMS_VERIFIED_BUYER"):
            reconcile(radar(c),new_state(),NOW)

    def test_health_degrades_for_partial_search(self):
        r=radar(candidate());r["errors"]=[{"query":"q1","error_type":"HTTPError"}]
        _,x=reconcile(r,new_state(),NOW)
        self.assertEqual(x["health"],"partial_data")

    def test_state_schema_failure(self):
        with tempfile.TemporaryDirectory() as p:
            file=Path(p)/"ledger.json"
            file.write_text('{"schema":"malicious","seen":{},"reviews":{}}')
            with self.assertRaisesRegex(ValueError,"INVALID_STATE_SCHEMA"):
                read_state(file)

    def test_cli_persists_state_without_duplicate_and_writes_decision(self):
        with tempfile.TemporaryDirectory() as p:
            d=Path(p); inp=d/"radar.json"; ledger=d/"state.json"; out=d/"decision.json"
            inp.write_text(json.dumps(radar(candidate())))
            args=["--radar",str(inp),"--state",str(ledger),"--out",str(out),"--now",NOW.isoformat()]
            self.assertEqual(run(args),0)
            before=ledger.read_bytes()
            self.assertEqual(run(args),0)
            self.assertEqual(ledger.read_bytes(),before)
            self.assertEqual(json.loads(out.read_text())["next_issue_url"],URL)

    def test_forged_payout_in_issue_not_promoted(self):
        c=candidate();c["title"]="SOLD $7m - click to claim payment";c["verified_revenue_usd"]=7000000
        _,x=reconcile(radar(c),new_state(),NOW)
        self.assertIsNone(x["verified_revenue_usd"])
        self.assertFalse(x["approval_to_contact"])

    def test_priority_is_score_and_never_contact(self):
        c=candidate(score=15)
        d=candidate(url="https://github.com/other/team/issues/8",score=20)
        _,x=reconcile(radar(c,d),new_state(),NOW)
        self.assertEqual(x["next_issue_url"],d["url"])
        self.assertFalse(x["approval_to_contact"])


if __name__ == "__main__":
    unittest.main()
