import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from products.agent_diff_gate import evaluate, main


class AgentDiffGateTests(unittest.TestCase):
    def make_pair(self, base, cand):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        p = root / "base.json"
        q = root / "new.json"
        p.write_text(json.dumps(base), encoding="utf-8")
        q.write_text(json.dumps(cand), encoding="utf-8")
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        return temp, p, q, digest

    def test_same_bytes_pass(self):
        t, a, b, h = self.make_pair({"ok": True}, {"ok": True})
        with t:
            result = evaluate(a, b, h)
            self.assertTrue(result["passed"])
            self.assertEqual(result["changed"], [])
            self.assertFalse(result["independent_buyer_approval_verified"])

    def test_unapproved_change_fails(self):
        t, a, b, h = self.make_pair({"result": 1}, {"result": 2})
        with t:
            result = evaluate(a, b, h)
            self.assertFalse(result["passed"])
            self.assertEqual(result["reason"], "UNAPPROVED_CHANGE")
            self.assertEqual(result["changed"][0]["path"], "/result")

    def test_bounded_allowed_change_passes(self):
        t, a, b, h = self.make_pair({"meta": {"review": 1}, "result": 1},
                                    {"meta": {"review": 2}, "result": 1})
        with t:
            self.assertTrue(evaluate(a, b, h, ["/meta"])["passed"])

    def test_prefix_does_not_allow_neighbor(self):
        t, a, b, h = self.make_pair({"metaX": 1}, {"metaX": 2})
        with t:
            self.assertFalse(evaluate(a, b, h, ["/meta"])["passed"])

    def test_tampered_baseline_fails_before_comparison(self):
        t, a, b, h = self.make_pair({"result": 1}, {"result": 1})
        with t:
            a.write_text('{"result":3}')
            result = evaluate(a, b, h)
            self.assertEqual(result["reason"], "BASELINE_DIGEST_MISMATCH")
            self.assertIsNone(result["candidate_sha256"])

    def test_duplicate_json_key_rejected(self):
        t, a, b, h = self.make_pair({"result": 1}, {"result": 1})
        with t:
            b.write_text('{"result":0,"result":1}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                evaluate(a, b, h)

    def test_bool_not_equal_to_integer(self):
        t, a, b, h = self.make_pair({"result": True}, {"result": 1})
        with t:
            self.assertFalse(evaluate(a, b, h)["passed"])

    def test_json_pointer_encoding(self):
        t, a, b, h = self.make_pair({"a/b~c": 1}, {"a/b~c": 2})
        with t:
            self.assertEqual(evaluate(a, b, h)["changed"][0]["path"], "/a~1b~0c")

    def test_array_change_path(self):
        t, a, b, h = self.make_pair([1], [1, 2])
        with t:
            self.assertEqual(evaluate(a, b, h)["changed"][0]["path"], "/1")

    def test_root_change_fails(self):
        t, a, b, h = self.make_pair(1, 2)
        with t:
            self.assertEqual(evaluate(a, b, h)["reason"], "UNAPPROVED_CHANGE")

    def test_root_allowlist_refused(self):
        t, a, b, h = self.make_pair({"a": 1}, {"a": 2})
        with t:
            with self.assertRaisesRegex(ValueError, "non-root"):
                evaluate(a, b, h, ["/"])

    def test_file_size_limit(self):
        t, a, b, h = self.make_pair({"result": 1}, {"result": 1})
        with t:
            b.write_text('"'+("x"*(512*1024))+'"')
            with self.assertRaisesRegex(ValueError, "exceeds"):
                evaluate(a, b, h)

    def test_nan_json_rejected(self):
        t, a, b, h = self.make_pair({"result": 1}, {"result": 1})
        with t:
            b.write_text('{"result":NaN}')
            with self.assertRaisesRegex(ValueError, "non-standard"):
                evaluate(a, b, h)

    def test_invalid_cli_exit_code(self):
        t, a, b, h = self.make_pair({"result": 1}, {"result": 2})
        with t:
            self.assertEqual(main([str(a), str(b), "--baseline-sha256", h]), 1)


if __name__ == "__main__":
    unittest.main()
