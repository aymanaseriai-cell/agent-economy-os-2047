import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from verifier import validate

class EvidenceTests(unittest.TestCase):
    def test_success(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'result.txt').write_text('hello')
            sha = hashlib.sha256(b'hello').hexdigest()
            m = root / 'm.json'
            m.write_text(json.dumps({'artifacts': [{'path': 'result.txt', 'sha256': sha}]}))
            self.assertTrue(validate(m, root)['passed'])

    def test_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'result.txt').write_text('hello')
            m = root / 'm.json'
            m.write_text(json.dumps({'artifacts': [{'path': 'result.txt', 'sha256': '0' * 64}]}))
            self.assertFalse(validate(m, root)['passed'])

    def test_path_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'project'
            root.mkdir()
            m = root / 'm.json'
            m.write_text(json.dumps({'artifacts': [{'path': '../outside', 'sha256': '0' * 64}]}))
            result = validate(m, root)
            self.assertFalse(result['passed'])
            self.assertIn('escapes', result['errors'][0])


    def test_duplicate_identical_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'artifact.txt').write_text('hello')
            digest = hashlib.sha256(b'hello').hexdigest()
            records = [
                {'path': 'artifact.txt', 'sha256': digest},
                {'path': 'artifact.txt', 'sha256': digest},
            ]
            m = root / 'duplicate.json'
            m.write_text(json.dumps({'artifacts': records}))
            report = validate(m, root)
            self.assertFalse(report['passed'])
            self.assertEqual(report['checked'], 1)
            self.assertIn('duplicate canonical artifact path', report['errors'][0])
            self.assertIn('artifacts[0]', report['errors'][0])

    def test_duplicate_dot_alias_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'artifact.txt').write_text('hello')
            digest = hashlib.sha256(b'hello').hexdigest()
            records = [
                {'path': 'artifact.txt', 'sha256': digest},
                {'path': './artifact.txt', 'sha256': digest},
            ]
            m = root / 'alias.json'
            m.write_text(json.dumps({'artifacts': records}))
            report = validate(m, root)
            self.assertFalse(report['passed'])
            self.assertEqual(report['checked'], 1)
            self.assertIn('duplicate canonical artifact path', report['errors'][0])

    def test_duplicate_symlink_alias_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'artifact.txt').write_text('hello')
            try:
                (root / 'alias.txt').symlink_to('artifact.txt')
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f'symlink unavailable: {exc}')
            digest = hashlib.sha256(b'hello').hexdigest()
            m = root / 'symlink.json'
            m.write_text(json.dumps({'artifacts': [
                {'path': 'artifact.txt', 'sha256': digest},
                {'path': 'alias.txt', 'sha256': digest},
            ]}))
            report = validate(m, root)
            self.assertFalse(report['passed'])
            self.assertEqual(report['checked'], 1)
            self.assertIn('duplicate canonical artifact path', report['errors'][0])

    def test_distinct_artifacts_still_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'a.txt').write_text('a')
            (root / 'b.txt').write_text('b')
            m = root / 'two-files.json'
            m.write_text(json.dumps({'artifacts': [
                {'path': 'a.txt', 'sha256': hashlib.sha256(b'a').hexdigest()},
                {'path': 'b.txt', 'sha256': hashlib.sha256(b'b').hexdigest()},
            ]}))
            report = validate(m, root)
            self.assertTrue(report['passed'])
            self.assertEqual(report['checked'], 2)


    def test_duplicate_top_level_artifacts_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'result.txt').write_text('hello')
            sha = hashlib.sha256(b'hello').hexdigest()
            m = root / 'ambiguous.json'
            m.write_text('{"artifacts":[{"path":"missing.txt","sha256":"%s"}],'
                         '"artifacts":[{"path":"result.txt","sha256":"%s"}]}' % (sha, sha))
            report = validate(m, root)
            self.assertFalse(report['passed'])
            self.assertIn('duplicate JSON key', report['errors'][0])

    def test_duplicate_nested_path_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'result.txt').write_text('hello')
            sha = hashlib.sha256(b'hello').hexdigest()
            m = root / 'ambiguous-path.json'
            m.write_text('{"artifacts":[{"path":"../outside","path":"result.txt",'
                         '"sha256":"%s"}]}' % sha)
            report = validate(m, root)
            self.assertFalse(report['passed'])
            self.assertIn('duplicate JSON key', report['errors'][0])

    def test_duplicate_nested_sha256_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'result.txt').write_text('hello')
            sha = hashlib.sha256(b'hello').hexdigest()
            m = root / 'ambiguous-hash.json'
            m.write_text('{"artifacts":[{"path":"result.txt","sha256":"%s",'
                         '"sha256":"%s"}]}' % ('0' * 64, sha))
            report = validate(m, root)
            self.assertFalse(report['passed'])
            self.assertIn('duplicate JSON key', report['errors'][0])


    def test_nonstandard_json_constants_fail_closed(self):
        # Python's default json.loads accepts these invalid JSON tokens.
        for constant in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(constant=constant):
                with tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    (root / 'result.txt').write_text('hello')
                    sha = hashlib.sha256(b'hello').hexdigest()
                    m = root / 'nonstandard.json'
                    m.write_text(
                        '{"artifacts":[{"path":"result.txt","sha256":"%s"}],'
                        '"metadata":{"confidence":%s}}' % (sha, constant)
                    )
                    report = validate(m, root)
                    self.assertFalse(report['passed'])
                    self.assertEqual(report['checked'], 0)
                    self.assertIn('non-standard JSON constant', report['errors'][0])


    def test_overflow_json_numbers_fail_closed(self):
        # parse_constant misses finite-looking numeric tokens that overflow Python float.
        for token in ('1e10000', '-1e10000', '9.99e9999'):
            with self.subTest(token=token):
                with tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    (root / 'result.txt').write_text('hello')
                    sha = hashlib.sha256(b'hello').hexdigest()
                    m = root / 'numeric-overflow.json'
                    m.write_text(
                        '{"artifacts":[{"path":"result.txt","sha256":"%s"}],'
                        '"metadata":{"confidence":%s}}' % (sha, token)
                    )
                    report = validate(m, root)
                    self.assertFalse(report['passed'])
                    self.assertEqual(report['checked'], 0)
                    self.assertIn('non-finite JSON number', report['errors'][0])

    def test_finite_json_numbers_still_pass(self):
        for token in ('1.25', '-0.5', '1e3'):
            with self.subTest(token=token):
                with tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    (root / 'result.txt').write_text('hello')
                    sha = hashlib.sha256(b'hello').hexdigest()
                    m = root / 'finite-number.json'
                    m.write_text(
                        '{"artifacts":[{"path":"result.txt","sha256":"%s"}],'
                        '"metadata":{"confidence":%s}}' % (sha, token)
                    )
                    report = validate(m, root)
                    self.assertTrue(report['passed'])

if __name__ == '__main__':
    unittest.main()
