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

    def test_duplicate_artifact_paths_do_not_inflate_checked_count(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "result.txt").write_text("hello")
            sha = hashlib.sha256(b"hello").hexdigest()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"artifacts": [
                {"path": "result.txt", "sha256": sha},
                {"path": "./result.txt", "sha256": sha},
            ]}))
            report = validate(manifest, root)
            self.assertFalse(report["passed"])
            self.assertEqual(report["checked"], 1)
            self.assertTrue(any("duplicate artifact path" in error for error in report["errors"]))

if __name__ == '__main__':
    unittest.main()
