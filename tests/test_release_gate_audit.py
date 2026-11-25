import copy
import unittest
from automation.release_gate_audit import audit, PR_URL, REVIEWS_URL, GATE_URL, WORKFLOWS, runs_url, ReviewError, OWNER, REPO

HEAD = "a" * 40
REPOSITORY = OWNER + "/" + REPO

def fixture():
    return {
        PR_URL: {"number": 114, "state": "open", "draft": False, "merged": False,
                 "head": {"sha": HEAD, "repo": {"full_name": REPOSITORY}}, "base": {"ref": "main"},
                 "user": {"login": OWNER}},
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

    def test_absence_of_external_review_is_not_a_blanket_blocker(self):
        f = fixture()
        f[REVIEWS_URL] = []
        result = run(f)
        self.assertEqual(result["independent_reviewers"], [])
        self.assertNotIn("NO_CURRENT_INDEPENDENT_COLLABORATOR_REVIEW", result["blockers"])
        self.assertIn("DOCUMENTED_SECURITY_REVIEW_REQUIRED", result["blockers"])
        self.assertIn("SOURCE_PARITY_REVIEW_REQUIRED", result["blockers"])
        self.assertIn("ROLLBACK_REVIEW_REQUIRED", result["blockers"])
        self.assertFalse(result["production_authorized"])
        self.assertEqual(result["writes"], 0)
        self.assertEqual(result["money_actions"], 0)

    def test_external_objection_remains_blocking_without_approval(self):
        f = fixture()
        f[REVIEWS_URL][0]["state"] = "CHANGES_REQUESTED"
        result = run(f)
        self.assertEqual(result["independent_reviewers"], [])
        self.assertIn("UNRESOLVED_INDEPENDENT_CHANGE_REQUEST", result["blockers"])
        self.assertIn("DOCUMENTED_SECURITY_REVIEW_REQUIRED", result["blockers"])
        self.assertFalse(result["production_authorized"])

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

    def test_codeql_scan_is_required_and_missing_fails_closed(self):
        scan = ".github/workflows/codeql-pr-security.yml"
        self.assertIn(scan, WORKFLOWS)
        f = fixture()
        f[runs_url(HEAD)]["workflow_runs"] = [
            run for run in f[runs_url(HEAD)]["workflow_runs"] if run["path"] != scan
        ]
        result = run(f)
        self.assertTrue(result["ci"][WORKFLOWS[0]]["passed"])
        self.assertFalse(result["ci"][scan]["passed"])
        self.assertIn("NO_CURRENT_CI:" + scan, result["blockers"])
        self.assertFalse(result["production_authorized"])

    def test_newest_codeql_failure_blocks_older_success(self):
        scan = ".github/workflows/codeql-pr-security.yml"
        f = fixture()
        older = next(x for x in f[runs_url(HEAD)]["workflow_runs"] if x["path"] == scan)
        newer = copy.deepcopy(older)
        newer.update({"id": 9999, "status": "completed", "conclusion": "failure"})
        f[runs_url(HEAD)]["workflow_runs"].append(newer)
        self.assertFalse(run(f)["ci"][scan]["passed"])

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

    def test_comment_does_not_erase_independent_objection(self):
        f = fixture()
        for state, number in (("CHANGES_REQUESTED", 101), ("COMMENTED", 102)):
            row = copy.deepcopy(f[REVIEWS_URL][0])
            row.update({"state": state, "id": number, "user": {"login": "second", "type": "User"}})
            f[REVIEWS_URL].append(row)
        result = run(f)
        self.assertEqual(result["independent_reviewers"], ["independent"])
        self.assertEqual(result["unresolved_change_request_reviewers"], ["second"])
        self.assertIn("UNRESOLVED_INDEPENDENT_CHANGE_REQUEST", result["blockers"])

    def test_pr_author_cannot_be_independent_even_if_not_owner(self):
        f = fixture()
        f[PR_URL]["user"] = {"login": "Independent"}
        self.assertEqual(run(f)["independent_reviewers"], [])

    def test_new_attempt_of_same_workflow_run_overrides_success(self):
        f = fixture()
        first = f[runs_url(HEAD)]["workflow_runs"][0]
        first["run_attempt"] = 1
        newer = copy.deepcopy(first)
        newer.update({"run_attempt": 2, "status": "in_progress", "conclusion": None})
        f[runs_url(HEAD)]["workflow_runs"].append(newer)
        self.assertFalse(run(f)["ci"][WORKFLOWS[0]]["passed"])

    def test_gate_reopened_during_audit_is_blocker(self):
        f = fixture()
        calls = []
        def get(url):
            row = copy.deepcopy(f[url])
            if url == GATE_URL:
                calls.append(1)
                if len(calls) == 2:
                    row["state"] = "open"
            return row
        result = audit(get)
        self.assertIn("GATE_CHANGED_DURING_AUDIT", result["blockers"])
        self.assertIn("P0_GATE_98_OPEN", result["blockers"])
        self.assertFalse(result["production_authorized"])

if __name__ == "__main__":
    unittest.main()
