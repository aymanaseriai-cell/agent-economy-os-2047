import copy
import unittest
from automation.release_gate_audit import audit, PR_URL, REVIEWS_URL, GATE_URL, WORKFLOWS, runs_url, ReviewError, OWNER, REPO

HEAD = "a" * 40
REPOSITORY = OWNER + "/" + REPO

def fixture():
    return {
        PR_URL: {"number": 114, "state": "open", "draft": False, "merged": False,
                 "head": {"sha": HEAD, "repo": {"full_name": REPOSITORY}}, "base": {"ref": "main"}},
        GATE_URL: {"number": 98, "state": "closed"},
        REVIEWS_URL: [{"id": 100, "submitted_at": "2026-11-22T05:00:00Z",
                       "user": {"login": "independent", "type": "User"},
                       "state": "APPROVED", "commit_id": HEAD, "author_association": "COLLABORATOR"}],
        runs_url(HEAD): {"workflow_runs": [
            {"head_sha": HEAD, "path": path, "event": "pull_request",
             "repository": {"full_name": REPOSITORY}, "id": n,
             "status": "completed", "conclusion": "success"}
            for n, path in enumerate(WORKFLOWS, 1000)]},
    }

def run(f):
    return audit(lambda url: copy.deepcopy(f[url]))

class ReleasePreflightTests(unittest.TestCase):
    def test_even_approved_healthy_ci_never_authorizes_release(self):
        result = run(fixture())
        self.assertTrue(all(v["passed"] for v in result["ci"].values()))
        self.assertEqual(result["independent_reviewers"], ["independent"])
        self.assertFalse(result["production_authorized"])
        self.assertIn("SOURCE_PARITY_REVIEW_REQUIRED", result["blockers"])

    def test_draft_open_gate_and_missing_independent_reviewer(self):
        f = fixture()
        f[PR_URL]["draft"] = True
        f[GATE_URL]["state"] = "open"
        f[REVIEWS_URL][0]["user"]["login"] = OWNER
        result = run(f)
        self.assertIn("DRAFT_PR", result["blockers"])
        self.assertIn("P0_GATE_98_OPEN", result["blockers"])
        self.assertEqual(result["independent_reviewers"], [])

    def test_stale_approval_and_bots_cannot_approve(self):
        for mutation in (
            {"commit_id": "b" * 40},
            {"user": {"login": "approver[bot]", "type": "Bot"}},
            {"state": "CHANGES_REQUESTED"},
        ):
            f = fixture()
            f[REVIEWS_URL][0].update(mutation)
            with self.subTest(mutation=mutation):
                self.assertEqual(run(f)["independent_reviewers"], [])

    def test_bad_repo_or_wrong_workflow_not_ci(self):
        for mutation in (
            {"repository": {"full_name": "attacker/other"}},
            {"path": ".github/workflows/other.yml"},
            {"conclusion": "failure"},
        ):
            f = fixture()
            f[runs_url(HEAD)]["workflow_runs"][0].update(mutation)
            with self.subTest(mutation=mutation):
                self.assertFalse(run(f)["ci"][WORKFLOWS[0]]["passed"])

    def test_newer_inprogress_check_overrides_old_success(self):
        f = fixture()
        newer = copy.deepcopy(f[runs_url(HEAD)]["workflow_runs"][0])
        newer.update({"id": 9999, "status": "in_progress", "conclusion": None})
        f[runs_url(HEAD)]["workflow_runs"].append(newer)
        self.assertFalse(run(f)["ci"][WORKFLOWS[0]]["passed"])

    def test_truncated_reviews_fail_closed(self):
        f = fixture()
        f[REVIEWS_URL] *= 100
        with self.assertRaisesRegex(ReviewError, "TRUNCATED"):
            run(f)

    def test_sha_path_traversal_not_allowed(self):
        f = fixture()
        f[PR_URL]["head"]["sha"] = "../anything"
        with self.assertRaisesRegex(ReviewError, "INVALID_HEAD_SHA"):
            run(f)

if __name__ == "__main__":
    unittest.main()
