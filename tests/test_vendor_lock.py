import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation"))
from verify_vendor_lock import check, duplicate_keys, REQUIRED, SCHEMA

class VendorLockTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.folder = self.root / "third_party" / "a2a"
        self.folder.mkdir(parents=True)
        self.assets = []
        for name in sorted(REQUIRED):
            content = b"fixture:" + name.encode()
            path = self.folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            self.assets.append({
                "path": name, "license": "Apache-2.0",
                "upstream_repository": "a2aproject/A2A",
                "source_commit": "a" * 40,
                "source_path": "specification/a2a.proto",
                "sha256": hashlib.sha256(content).hexdigest(),
            })
        self.lock = {"schema": SCHEMA, "assets": self.assets}

    def tearDown(self):
        self.temporary.cleanup()

    def test_matching_files_pass(self):
        result = check(self.root, self.lock)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verified"], 4)
        self.assertFalse(result["upstream_identity_verified"])

    def test_tampered_file_fails(self):
        (self.folder / "specification/a2a.proto").write_bytes(b"modified")
        self.assertFalse(check(self.root, self.lock)["ok"])

    def test_missing_file_fails(self):
        (self.folder / "LICENSE").unlink()
        self.assertFalse(check(self.root, self.lock)["ok"])

    def test_duplicate_path_fails(self):
        lock = copy.deepcopy(self.lock)
        lock["assets"].append(copy.deepcopy(lock["assets"][0]))
        self.assertFalse(check(self.root, lock)["ok"])

    def test_missing_asset_in_lock_fails(self):
        lock = copy.deepcopy(self.lock)
        lock["assets"].pop()
        self.assertFalse(check(self.root, lock)["ok"])

    def test_wrong_license_fails(self):
        lock = copy.deepcopy(self.lock)
        lock["assets"][0]["license"] = "Unknown"
        self.assertFalse(check(self.root, lock)["ok"])

    def test_bad_commit_fails(self):
        lock = copy.deepcopy(self.lock)
        lock["assets"][0]["source_commit"] = "main"
        self.assertFalse(check(self.root, lock)["ok"])

    def test_unexpected_traversal_name_fails(self):
        lock = copy.deepcopy(self.lock)
        lock["assets"][0]["path"] = "../../outside"
        self.assertFalse(check(self.root, lock)["ok"])

    def test_unexpected_extra_property_fails(self):
        lock = copy.deepcopy(self.lock)
        lock["assets"][0]["sneaky"] = True
        self.assertFalse(check(self.root, lock)["ok"])

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"x":1,"x":2}', object_pairs_hook=duplicate_keys)

if __name__ == "__main__":
    unittest.main()
