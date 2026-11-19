import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from verifier import validate


class EvidenceSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'result.txt').write_text('hello', encoding='utf-8')
        self.sha = hashlib.sha256(b'hello').hexdigest()
        self.manifest = self.root / 'm.json'

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, rows):
        self.manifest.write_text(json.dumps({'artifacts': rows}), encoding='utf-8')
        return validate(self.manifest, self.root)

    def test_valid_sample_preserved(self):
        r = self.save([{'path':'result.txt','sha256':self.sha}])
        self.assertTrue(r['passed'])
        self.assertEqual(r['checked'], 1)

    def test_hash_mismatch_still_rejected(self):
        self.assertFalse(self.save([{'path':'result.txt','sha256':'0'*64}])['passed'])

    def test_path_escape_still_rejected(self):
        r = self.save([{'path':'../outside','sha256':self.sha}])
        self.assertFalse(r['passed'])
        self.assertIn('escapes',r['errors'][0])

    def test_duplicate_file_alias_rejected(self):
        r = self.save([{'path':'result.txt','sha256':self.sha},{'path':'./result.txt','sha256':self.sha}])
        self.assertFalse(r['passed'])
        self.assertEqual(r['checked'],1)
        self.assertIn('duplicate artifact path',r['errors'][0])

    def test_duplicate_json_root_key_rejected(self):
        self.manifest.write_text('{"artifacts":[],"artifacts":[{"path":"result.txt","sha256":"'+self.sha+'"}]}')
        r=validate(self.manifest,self.root)
        self.assertFalse(r['passed'])
        self.assertIn('duplicate JSON key',r['errors'][0])

    def test_duplicate_json_nested_key_rejected(self):
        self.manifest.write_text('{"artifacts":[{"path":"escape","path":"result.txt","sha256":"'+self.sha+'"}]}')
        r=validate(self.manifest,self.root)
        self.assertFalse(r['passed'])
        self.assertIn('duplicate JSON key',r['errors'][0])

    def test_embedded_nul_graceful_failure(self):
        r=self.save([{'path':'foo\x00bar','sha256':self.sha}])
        self.assertFalse(r['passed'])
        self.assertIn('invalid file path',r['errors'][0])

    def test_symlink_alias_rejected(self):
        (self.root / 'shortcut.txt').symlink_to(self.root/'result.txt')
        r=self.save([{'path':'result.txt','sha256':self.sha},{'path':'shortcut.txt','sha256':self.sha}])
        self.assertFalse(r['passed'])
        self.assertIn('duplicate artifact path',r['errors'][0])


if __name__ == '__main__': unittest.main()
