import json
import tempfile
import unittest
from pathlib import Path
from automation.worker_dispatcher import (
    dispatch, evaluate, PolicyError, main, safe_local_file, _fetch_open_issues,
    _open_inbound_snapshot, GITHUB_ISSUES_LIST, MAX_ISSUE_PAGES, default_fetch
)

SHA = "b56e5946b63d22eda34599ae119fc24fca3f9a1f"


def task(kind="github_ci_readonly", role="CTO", payload=None, **kw):
    if payload is None:
        payload = {"run_id": 44875982406, "expected_head_sha": SHA}
    return {"id": "CTO-CHECK-1", "role": role, "kind": kind, "payload": payload, **kw}


class WorkerDispatchTests(unittest.TestCase):
    def test_valid_ci_receipt_is_rechecked(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return {"status": "completed", "conclusion": "success", "head_sha": SHA, "html_url": "https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/runs/44875982406",
                    "path": ".github/workflows/ci.yml",
                    "repository": {"full_name": "aymanaseriai-cell/agent-economy-os-2047"}}
        result = dispatch(task(), Path("."), fetch)
        self.assertEqual(result["status"], "VERIFIED_READONLY")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(len(calls), 2)
        self.assertFalse(result["outbound_contact"])

    def test_changed_provider_receipt_blocked_after_bounded_retry(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return {"status": "completed", "conclusion": "success", "head_sha": SHA if len(calls) % 2 else "a"*40, "html_url": "https://github.com/...",
                    "path": ".github/workflows/ci.yml",
                    "repository": {"full_name": "aymanaseriai-cell/agent-economy-os-2047"}}
        result = dispatch(task(), Path("."), fetch)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(len(calls), 4)

    def test_failed_ci_not_success(self):
        def fetch(url):
            return {"status": "completed", "conclusion": "failure", "head_sha": SHA, "html_url": "https://github.com/...",
                    "path": ".github/workflows/ci.yml",
                    "repository": {"full_name": "aymanaseriai-cell/agent-economy-os-2047"}}
        result = dispatch(task(), Path("."), fetch)
        self.assertEqual(result["verification"], "CI_NOT_PASSING_ON_EXPECTED_SHA")
        self.assertEqual(result["status"], "BLOCKED")

    def test_other_workflow_or_other_repository_cannot_forge_ci_success(self):
        base = {"status": "completed", "conclusion": "success", "head_sha": SHA,
                "path": ".github/workflows/ci.yml",
                "repository": {"full_name": "aymanaseriai-cell/agent-economy-os-2047"}}
        cases = [
            {"path": ".github/workflows/worker-fleet-readonly.yml"},
            {"repository": {"full_name": "untrusted/repository"}},
            {"repository": None},
            {"path": None},
        ]
        for mutation in cases:
            with self.subTest(mutation=mutation):
                doc = dict(base, **mutation)
                result = dispatch(task(), Path("."), lambda url: doc)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertEqual(result["verification"], "CI_NOT_PASSING_ON_EXPECTED_SHA")

    def test_external_issue_is_not_buyer_or_contact_permission(self):
        doc = {"number": 77, "state": "open", "user": {"login": "real-elsewhere", "type": "User"}, "title": "[Service request] Audit"}
        inbound = task("github_inbound_readonly", "CRO", {"issue_number": 77})
        result = dispatch(inbound, Path("."), lambda url: doc)
        self.assertEqual(result["status"], "VERIFIED_READONLY")
        self.assertTrue(result["evidence"]["outside_opt_in_candidate"])
        self.assertFalse(result["evidence"]["verified_buyer"])
        self.assertFalse(result["evidence"]["contact_authorized"])


    def test_discovers_real_opt_in_on_second_page(self):
        page1 = [{"number": n, "state": "open", "title": "[Service request] Owner",
                  "user": {"login": "aymanaseriai-cell", "type": "User"}}
                 for n in range(1, 101)]
        page2 = [{"number": 1234, "state": "open", "title": "[Service request] External",
                  "user": {"login": "real-external", "type": "User"}}]
        calls = []
        def fetch(url):
            calls.append(url)
            return page1 if url == GITHUB_ISSUES_LIST else page2
        r = dispatch(task("github_issues_readonly", "CRO", {}), Path("."), fetch)
        self.assertEqual(r["status"], "VERIFIED_READONLY")
        self.assertEqual(r["evidence"]["candidate_count"], 1)
        self.assertEqual(r["evidence"]["eligible_external_candidates"][0]["issue_number"], 1234)
        self.assertEqual(calls.count(GITHUB_ISSUES_LIST + "&page=2"), 2)
        self.assertFalse(r["evidence"]["verified_paid_buyers"])

    def test_bot_with_human_sounding_login_is_not_external_buyer(self):
        bot = {"number": 70, "state": "open", "title": "[Service request] Bot",
               "user": {"login": "helper-person", "type": "Bot"}}
        self.assertEqual(_open_inbound_snapshot([bot])["candidate_count"], 0)
        result = dispatch(task("github_inbound_readonly", "CRO", {"issue_number": 70}),
                          Path("."), lambda url: bot)
        self.assertFalse(result["evidence"]["outside_opt_in_candidate"])
        missing_type = dict(bot, user={"login": "real-external"})
        self.assertEqual(_open_inbound_snapshot([missing_type])["candidate_count"], 0)

    def test_full_fifth_page_fails_closed(self):
        called = []
        def fetch(url):
            called.append(url)
            page = 1 if url == GITHUB_ISSUES_LIST else int(url.rsplit("=", 1)[1])
            return [{"number": page * 1000 + i} for i in range(100)]
        with self.assertRaisesRegex(PolicyError, "INBOUND_PAGINATION_INCOMPLETE"):
            _fetch_open_issues(fetch)
        self.assertEqual(len(called), MAX_ISSUE_PAGES)

    def test_overlap_between_pages_fails_closed(self):
        first = [{"number": i} for i in range(1, 101)]
        with self.assertRaisesRegex(PolicyError, "UNSTABLE_ISSUE_PAGINATION"):
            _fetch_open_issues(lambda url: first if url == GITHUB_ISSUES_LIST else [{"number": 1}])

    def test_unapproved_sixth_page_rejected_without_network(self):
        from unittest.mock import patch
        with patch("automation.worker_dispatcher.build_opener") as opener:
            with self.assertRaisesRegex(PolicyError, "URL_NOT_ALLOWLISTED"):
                default_fetch(GITHUB_ISSUES_LIST + "&page=6")
            opener.assert_not_called()

    def test_owner_issue_does_not_fake_external_adoption(self):
        doc = {"number": 112, "state": "open", "user": {"login": "aymanaseriai-cell", "type": "User"}, "title": "[Service request] Audit"}
        result = dispatch(task("github_inbound_readonly", "CRO", {"issue_number": 112}), Path("."), lambda url: doc)
        self.assertFalse(result["evidence"]["outside_opt_in_candidate"])

    def test_permitted_local_digest_recomputed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "safe.json"; p.write_text('{"value":1}')
            t = task("local_file_digest", "CTO", {"path": "safe.json"})
            result = dispatch(t, Path(d))
            self.assertEqual(result["status"], "VERIFIED_READONLY")
            self.assertEqual(result["evidence"]["bytes"], 11)

    def test_denies_traversal_symlink_and_absolute_path(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "link").symlink_to("/etc/passwd")
            for path in ("../foo", "/etc/passwd", "link"):
                with self.subTest(path=path), self.assertRaises(PolicyError):
                    safe_local_file(base, path)

    def test_denies_unapproved_roles_writes_and_spend(self):
        for t in (task(role="CRO"), task(spend_usd=1), task(allow_write=True), task(max_attempts=0)):
            with self.subTest(t=t), self.assertRaises(PolicyError):
                evaluate(t)

    def test_no_unbounded_attempts(self):
        with self.assertRaises(PolicyError):
            evaluate(task(max_attempts=99))

    def test_real_work_covenant_health_shape_is_verified(self):
        calls = []
        response = {"ok": True, "service": "agent-work-covenant-2047",
                    "stateless": True, "no_paid_actions": True}
        def fetch(url):
            calls.append(url)
            return response
        checked = dispatch(task("http_health_readonly", "COO_CFO", {}), Path("."), fetch)
        self.assertEqual(checked["status"], "VERIFIED_READONLY")
        self.assertEqual(checked["evidence"]["reported_health"], "healthy")
        self.assertFalse(checked["evidence"]["production_release_authorized"])
        self.assertEqual(len(calls), 2)

    def test_unknown_or_contradictory_health_fails_closed(self):
        health_task = task("http_health_readonly", "COO_CFO", {})
        samples = (
            {"unexpected": "JSON not evidence of service health"},
            {"ok": True, "service": "agent-work-covenant-2047"},
            {"ok": False, "status": "ok", "service": "agent-work-covenant-2047",
             "stateless": True, "no_paid_actions": True},
            {"status": "degraded", "service": "other"},
            {"status": "healthy"},
            {"status": "ok", "service": "another-service", "ok": True,
             "stateless": True, "no_paid_actions": True},
            {"status": "healthy", "service": "agent-work-covenant-2047",
             "ok": True, "no_paid_actions": True},
            {"ok": True, "service": "agent-work-covenant-2047",
             "stateless": "true", "no_paid_actions": True},
        )
        for document in samples:
            with self.subTest(document=document):
                result = dispatch(health_task, Path("."), lambda url: document)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertEqual(result["attempts"], 2)
                self.assertEqual(result["verification"], "HEALTH_NOT_CONFIRMED")

    def test_provider_json_body_size_is_bounded_before_parse(self):
        import io
        from unittest.mock import patch
        from automation.worker_dispatcher import default_fetch, GITHUB_ISSUES_LIST, MAX_BYTES
        with patch("automation.worker_dispatcher.build_opener") as mocked:
            mocked.return_value.open.return_value = io.BytesIO(b'{"ok": true}')
            self.assertEqual(default_fetch(GITHUB_ISSUES_LIST), {"ok": True})
        with patch("automation.worker_dispatcher.build_opener") as mocked:
            mocked.return_value.open.return_value = io.BytesIO(b" " * (MAX_BYTES + 1))
            with self.assertRaisesRegex(PolicyError, "PROVIDER_BODY_TOO_LARGE"):
                default_fetch(GITHUB_ISSUES_LIST)

    def test_provider_redirect_is_denied_before_token_leak(self):
        from urllib.request import Request
        from unittest.mock import patch
        from automation.worker_dispatcher import _DenyRedirects, default_fetch, GITHUB_ISSUES_LIST
        request = Request(GITHUB_ISSUES_LIST, headers={"Authorization": "Bearer fake-token"})
        with self.assertRaisesRegex(PolicyError, "PROVIDER_REDIRECT_NOT_ALLOWLISTED"):
            _DenyRedirects().redirect_request(
                request, None, 302, "Found", {},
                "https://not-an-approved-provider.example/capture"
            )
        with patch("automation.worker_dispatcher.build_opener") as mocked:
            mocked.return_value.open.side_effect = PolicyError("PROVIDER_REDIRECT_NOT_ALLOWLISTED")
            with self.assertRaisesRegex(PolicyError, "PROVIDER_REDIRECT_NOT_ALLOWLISTED"):
                default_fetch(GITHUB_ISSUES_LIST)
            self.assertIsInstance(mocked.call_args.args[0], _DenyRedirects)

    def test_cli_writes_true_receipt_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); (base / "f").write_text("hello")
            t = task("local_file_digest", "CTO", {"path": "f"})
            file = base / "tasks.json"; file.write_text(json.dumps([t]))
            out = base / "receipt.json"
            self.assertEqual(main(["--tasks", str(file), "--root", d, "--out", str(out)]), 0)
            report = json.loads(out.read_text())
            self.assertEqual(report["receipts"][0]["status"], "VERIFIED_READONLY")
            file.write_text(json.dumps([t,t]))
            self.assertEqual(main(["--tasks", str(file), "--root", d, "--out", str(out)]), 2)


if __name__ == "__main__":
    unittest.main()
