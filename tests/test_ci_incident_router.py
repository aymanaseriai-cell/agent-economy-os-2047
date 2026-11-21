import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation"))
from ci_incident_router import process, MARKER, PREFIX

REPO = "aymanaseriai-cell/agent-economy-os-2047"
SHA = "a" * 40


def event(conclusion="failure", sha=SHA):
    return {
        "action": "completed",
        "workflow_run": {
            "name": "Test and verify", "head_branch": "main", "head_sha": sha,
            "conclusion": conclusion,
            "html_url": f"https://github.com/{REPO}/actions/runs/112233",
            "head_repository": {"full_name": REPO},
        }
    }


class API:
    def __init__(self, issues=None, latest=SHA):
        self.issues = [] if issues is None else issues
        self.latest = latest
        self.writes = []

    def __call__(self, path, method="GET", payload=None):
        if method != "GET":
            self.writes.append((method, path, payload))
            return {}
        if path.endswith("/commits/main"):
            return {"sha": self.latest}
        if "/issues?state=open" in path:
            return self.issues
        raise AssertionError("unexpected request: " + path)


def bot_issue(number=100):
    return {
        "number": number, "title": PREFIX + " main " + SHA[:12],
        "body": MARKER, "user": {"login": "github-actions[bot]"},
    }


class CIIssueRouterTests(unittest.TestCase):
    def test_current_main_failure_creates_one_cto_issue(self):
        api = API()
        self.assertEqual(process(event(), api, REPO), "CREATED_CTO_INCIDENT")
        self.assertEqual(len(api.writes), 1)
        self.assertEqual(api.writes[0][0], "POST")
        self.assertEqual(api.writes[0][1], f"/repos/{REPO}/issues")
        self.assertIn("Never auto-merge", api.writes[0][2]["body"])

    def test_duplicate_failure_does_not_spam(self):
        api = API(issues=[bot_issue()])
        self.assertEqual(process(event(), api, REPO), "EXISTS")
        self.assertEqual(api.writes, [])

    def test_stale_main_sha_does_not_open_issue(self):
        api = API(latest="b" * 40)
        self.assertEqual(process(event(), api, REPO), "IGNORED_SUPERSEDED_MAIN")
        self.assertEqual(api.writes, [])

    def test_external_repository_never_used(self):
        api = API()
        x = event()
        x["workflow_run"]["head_repository"]["full_name"] = "attacker/fork"
        self.assertEqual(process(x, api, REPO), "IGNORED_EXTERNAL_REPOSITORY")
        self.assertEqual(api.writes, [])

    def test_success_closes_only_bot_created_issue(self):
        human = {
            "number": 55, "title": PREFIX + " main " + SHA[:12],
            "body": MARKER, "user": {"login": "real-reporter"},
        }
        api = API(issues=[bot_issue(), human])
        self.assertEqual(process(event("success"), api, REPO), "CURRENT_MAIN_PASS_CLOSED_1")
        self.assertEqual(len(api.writes), 2)
        self.assertTrue(all("/issues/100" in write[1] for write in api.writes))
        self.assertEqual(api.writes[-1][2], {"state": "closed"})

    def test_missing_url_fails_closed(self):
        api = API()
        x = event()
        x["workflow_run"]["html_url"] = "https://malicious.invalid/run"
        self.assertEqual(process(x, api, REPO), "IGNORED_INVALID_RUN_URL")
        self.assertFalse(api.writes)

    def test_missing_issue_page_fails_closed(self):
        api = API(issues=[{}] * 100)
        self.assertEqual(process(event(), api, REPO), "BLOCKED_INCOMPLETE_ISSUE_PAGE")
        self.assertFalse(api.writes)

    def test_unrelated_job_does_not_trigger_issue(self):
        api = API()
        x = event()
        x["workflow_run"]["name"] = "Other workflow"
        self.assertEqual(process(x, api, REPO), "IGNORED_UNSCOPED_WORKFLOW")
        self.assertFalse(api.writes)


if __name__ == "__main__":
    unittest.main()
