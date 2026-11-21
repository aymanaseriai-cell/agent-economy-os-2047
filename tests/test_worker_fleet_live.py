import unittest
from automation.worker_fleet_live import prepare_live_jobs, LivePlanError
from automation.worker_dispatcher import MAIN_BRANCH_URL, MAIN_CI_RUNS_URL, GITHUB_ISSUES_LIST

HEAD = "b56e5946b63d22eda34599ae119fc24fca3f9a1f"


def provider(url, external=True, matched=True, conclusion="success"):
    if url == MAIN_BRANCH_URL:
        return {"commit": {"sha": HEAD}}
    if url == MAIN_CI_RUNS_URL:
        return {"workflow_runs": [{"id": 44875982406, "head_sha": HEAD if matched else "a"*40,
                                   "status": "completed", "conclusion": conclusion}]}
    if url == GITHUB_ISSUES_LIST:
        base = [{"number": 112, "state": "open", "title": "[Public opt-in offer] $49",
                 "user": {"login": "aymanaseriai-cell"}}]
        if external:
            base.append({"number": 123, "state": "open", "title": "[Service request] Scope",
                         "user": {"login": "nonowner-requester"}})
        return base
    raise ValueError("INVALID_URL")


class LivePlanTests(unittest.TestCase):
    def test_current_main_12_unique_jobs(self):
        x = prepare_live_jobs(provider)
        self.assertEqual(len(x["jobs"]), 12)
        self.assertEqual(len({y["worker_id"] for y in x["jobs"]}), 12)
        self.assertEqual(x["candidate_count"], 1)
        self.assertEqual(next(j for j in x["jobs"] if j["worker_id"] == "AEOS-W08")["payload"]["issue_number"], 123)
        self.assertIsNone(x["verified_revenue_usd"])

    def test_owner_invitation_is_not_a_customer(self):
        x = prepare_live_jobs(lambda url: provider(url, external=False))
        self.assertEqual(x["candidate_count"], 0)
        self.assertEqual(next(j for j in x["jobs"] if j["worker_id"] == "AEOS-W08")["payload"]["issue_number"], 112)

    def test_stale_run_rejected(self):
        with self.assertRaisesRegex(LivePlanError, "NO_COMPLETED_CI_FOR_CURRENT_MAIN"):
            prepare_live_jobs(lambda url: provider(url, matched=False))

    def test_failed_ci_not_turned_into_success(self):
        x = prepare_live_jobs(lambda url: provider(url, conclusion="failure"))
        self.assertEqual(x["ci_run"], 44875982406)

    def test_bad_commit_id_rejected(self):
        def bad(url):
            if url == MAIN_BRANCH_URL:
                return {"commit": {"sha": "unknown"}}
            return provider(url)
        with self.assertRaisesRegex(LivePlanError, "MAIN_SHA_NOT_VERIFIED"):
            prepare_live_jobs(bad)


if __name__ == "__main__":
    unittest.main()
