import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'automation'))
from repo_audit import analyze, markdown_report
from issue_router import find_repo, build_response


def fake_fetch(path):
    if '/git/trees/' in path:
        return {"truncated": False, "tree": [{"path": name, "type": "blob"} for name in [
            'README.md', 'LICENSE', 'SECURITY.md', '.github/workflows/ci.yml',
            '.github/ISSUE_TEMPLATE/free-repo-audit.yml', '.github/dependabot.yml']]}
    return {"private": False, "default_branch": "main", "description": "demo", "license": {"key": "mit"}}


class RepoAuditTests(unittest.TestCase):
    def test_all_signals(self):
        report = analyze('example/demo', fetch=fake_fetch)
        self.assertEqual(report['score'], 100)
        self.assertIn('100/100', markdown_report(report))

    def test_no_private_repos(self):
        with self.assertRaisesRegex(ValueError, 'public'):
            analyze('example/private', fetch=lambda path: {"private": True})

    def test_bad_slugs(self):
        for x in ['https://evil.com/x', 'x/../../bad', 'x/y?evil=1', 'x/y/z']:
            with self.subTest(x=x), self.assertRaises(ValueError):
                analyze(x, fetch=fake_fetch)

    def test_issue_slug(self):
        self.assertEqual(find_repo('### Public GitHub repository\n\nhttps://github.com/acme/demo.git\n'), 'acme/demo')
        self.assertIsNone(find_repo('my private repo'))

    def test_response_contains_real_audit_not_paid_claim(self):
        response = build_response({"title": "[Free audit] test", "body": "https://github.com/example/demo"}, fetch=fake_fetch)
        self.assertIn('100/100', response)
        self.assertIn('No payment is taken', response)

    def test_does_not_respond_unrelated(self):
        self.assertIsNone(build_response({'title': 'Bug: broken'}))

if __name__ == '__main__':
    unittest.main()
