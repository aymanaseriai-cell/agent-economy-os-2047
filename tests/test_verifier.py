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


    def test_duplicate_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'a.txt').write_bytes(b'a')
            record = {'path': 'a.txt', 'sha256': hashlib.sha256(b'a').hexdigest()}
            m = root / 'm.json'
            m.write_text(json.dumps({'artifacts': [record, record]}))
            result = validate(m, root)
            self.assertFalse(result['passed'])
            self.assertIn('duplicate artifact path', str(result['errors']))

    def test_ambiguous_paths_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for bad in ('a/../b', './b', 'a//b', '/etc/passwd', 'C:\\\\secrets.txt'):
                with self.subTest(path=bad):
                    m = root / 'm.json'
                    m.write_text(json.dumps({'artifacts': [{'path': bad, 'sha256': '0' * 64}]}))
                    self.assertFalse(validate(m, root)['passed'])

    def test_directory_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'real').mkdir()
            (root / 'real' / 'file.txt').write_bytes(b'hello')
            try:
                (root / 'alias').symlink_to(root / 'real', target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest('symlink not available')
            m = root / 'm.json'
            m.write_text(json.dumps({'artifacts': [{'path': 'alias/file.txt', 'sha256': hashlib.sha256(b'hello').hexdigest()}]}))
            self.assertFalse(validate(m, root)['passed'])

    def test_hardlink_alias_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'a.txt').write_bytes(b'a')
            try:
                (root / 'b.txt').hardlink_to(root / 'a.txt')
            except (OSError, NotImplementedError):
                self.skipTest('hardlinks not available')
            digest = hashlib.sha256(b'a').hexdigest()
            m = root / 'm.json'
            m.write_text(json.dumps({'artifacts': [{'path': n, 'sha256': digest} for n in ('a.txt', 'b.txt')]}))
            result = validate(m, root)
            self.assertFalse(result['passed'])
            self.assertIn('duplicate underlying file', str(result['errors']))

    def test_named_pipe_rejected(self):
        import os
        if not hasattr(os, 'mkfifo'):
            self.skipTest('FIFO not available')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            os.mkfifo(root / 'pipe')
            m = root / 'm.json'
            m.write_text(json.dumps({'artifacts': [{'path': 'pipe', 'sha256': '0' * 64}]}))
            result = validate(m, root)
            self.assertFalse(result['passed'])
            self.assertIn('regular', str(result['errors']))

if __name__ == '__main__':
    unittest.main()
