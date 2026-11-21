import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "buyer-gate"))
from check import SCHEMA, check, pointer_value, protected_file, load_policy, GateError


class BuyerPinnedGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name)
        (self.p / "outputs").mkdir()
        (self.p / "outputs" / "answer.json").write_text('{"result":"approved","ok":true,"count":2}', encoding="utf-8")
        self.policy = {
            "schema": SCHEMA,
            "requirements": [
                {"id": "file_present", "type": "file_exists", "path": "outputs/answer.json"},
                {"id": "result_status", "type": "json_pointer_equals", "path": "outputs/answer.json", "pointer": "/result", "expected": "approved"},
                {"id": "text_found", "type": "text_contains", "path": "outputs/answer.json", "needle": '"count":2'},
            ],
        }

    def save(self, p=None):
        self.path = self.p / "policy.json"
        self.path.write_text(json.dumps(p if p is not None else self.policy), encoding="utf-8")
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def run_gate(self):
        return check(self.path, self.p, self.pin)

    def test_positive_pin_and_all_three_checks(self):
        self.pin = self.save()
        x = self.run_gate()
        self.assertTrue(x["local_checks_passed"])
        self.assertTrue(x["policy_pin_matched"])
        self.assertFalse(x["buyer_authority_verified"])
        self.assertFalse(x["source_freshness_verified"])
        self.assertFalse(x["payment_verified"])

    def test_producer_changes_policy_without_pin(self):
        self.pin = self.save()
        self.policy["requirements"][1]["expected"] = "tampered"
        self.save()
        x = self.run_gate()
        self.assertEqual(x["errors"], ["POLICY_PIN_MISMATCH"])
        self.assertFalse(x["local_checks_passed"])

    def test_producer_changes_output(self):
        self.pin = self.save()
        (self.p / "outputs" / "answer.json").write_text('{"result":"tampered","count":2}', encoding="utf-8")
        x = self.run_gate()
        self.assertFalse(x["local_checks_passed"])
        self.assertEqual(x["results"][1]["result"], "FAIL")

    def test_explicit_digest_matches_and_detects_change(self):
        content = (self.p / "outputs" / "answer.json").read_bytes()
        self.policy["requirements"].append({
            "id": "known_digest", "type": "file_sha256", "path": "outputs/answer.json",
            "expected_sha256": hashlib.sha256(content).hexdigest()
        })
        self.pin = self.save()
        self.assertTrue(self.run_gate()["local_checks_passed"])
        (self.p / "outputs" / "answer.json").write_text('{"result":"approved","ok":true,"count":3}')
        self.assertFalse(self.run_gate()["local_checks_passed"])

    def test_reject_symlink_to_outside(self):
        (self.p / "outputs" / "link.json").symlink_to(self.p / "outputs" / "answer.json")
        self.policy["requirements"][0]["path"] = "outputs/link.json"
        self.pin = self.save()
        self.assertIn("SYMLINK_NOT_ALLOWED", self.run_gate()["errors"])

    def test_reject_path_traversal(self):
        self.policy["requirements"][0]["path"] = "../secret"
        self.pin = self.save()
        self.assertEqual(self.run_gate()["errors"], ["INVALID_ARTIFACT_PATH"])

    def test_reject_absolute_path(self):
        self.policy["requirements"][0]["path"] = "/etc/passwd"
        self.pin = self.save()
        self.assertEqual(self.run_gate()["errors"], ["INVALID_ARTIFACT_PATH"])

    def test_reject_duplicate_ids(self):
        self.policy["requirements"][1]["id"] = "file_present"
        self.pin = self.save()
        self.assertEqual(self.run_gate()["errors"], ["INVALID_OR_DUPLICATE_ID"])

    def test_unknown_type_denied(self):
        self.policy["requirements"][1]["type"] = "execute_shell"
        self.pin = self.save()
        self.assertEqual(self.run_gate()["errors"], ["UNSUPPORTED_REQUIREMENT"])

    def test_invalid_policy_pin_denied(self):
        self.save()
        r = check(self.path, self.p, "not_a_digest")
        self.assertEqual(r["errors"], ["INVALID_POLICY_PIN"])

    def test_missing_file_denied(self):
        self.policy["requirements"][0]["path"] = "outputs/absent.json"
        self.pin = self.save()
        self.assertFalse(self.run_gate()["local_checks_passed"])

    def test_json_boolean_is_not_number(self):
        self.policy["requirements"][1]["pointer"] = "/ok"
        self.policy["requirements"][1]["expected"] = 1
        self.pin = self.save()
        self.assertEqual(self.run_gate()["results"][1]["result"], "FAIL")

    def test_json_pointer_escapes_and_array(self):
        x = {"a/b": {"~key": ["ok", "done"]}}
        self.assertEqual(pointer_value(x, "/a~1b/~0key/1"), "done")

    def test_invalid_json_pointer_raises(self):
        with self.assertRaises(GateError):
            pointer_value({}, "/bad~3")

    def test_fail_large_file(self):
        (self.p / "outputs" / "answer.json").write_bytes(b"x" * (4 * 1024 * 1024 + 1))
        self.pin = self.save()
        self.assertFalse(self.run_gate()["local_checks_passed"])

    def test_no_policy_authorship_claim(self):
        self.pin = self.save()
        x = self.run_gate()
        self.assertFalse(x["buyer_identity_verified"])
        self.assertFalse(x["independent_provenance_verified"])
        self.assertFalse(x["agent_execution_verified"])

    def test_reject_empty_requirements(self):
        self.policy["requirements"] = []
        self.pin = self.save()
        self.assertEqual(self.run_gate()["errors"], ["INVALID_REQUIREMENT_COUNT"])

    def test_path_inside_subdirectory_symlink_rejected(self):
        (self.p / "linked").symlink_to(self.p / "outputs", target_is_directory=True)
        self.policy["requirements"][0]["path"] = "linked/answer.json"
        self.pin = self.save()
        self.assertEqual(self.run_gate()["errors"], ["SYMLINK_NOT_ALLOWED"])


    def test_duplicate_artifact_json_keys_fail_closed(self):
        self.pin = self.save()
        (self.p / "outputs" / "answer.json").write_text(
            '{"result":"denied","result":"approved","ok":true,"count":2}', encoding="utf-8"
        )
        report = self.run_gate()
        self.assertFalse(report["local_checks_passed"])
        self.assertEqual(report["results"][1]["reason"], "DUPLICATE_JSON_KEY")

    def test_duplicate_policy_json_keys_fail_closed(self):
        self.pin = self.save()
        original = self.path.read_text(encoding="utf-8")
        self.path.write_text(
            original.replace('"schema":', '"schema": "untrusted", "schema":', 1),
            encoding="utf-8",
        )
        self.pin = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertEqual(self.run_gate()["errors"], ["DUPLICATE_JSON_KEY"])

    def test_nonfinite_artifact_json_fails_closed(self):
        self.pin = self.save()
        (self.p / "outputs" / "answer.json").write_text(
            '{"result":"approved","ok":true,"count":NaN}', encoding="utf-8"
        )
        report = self.run_gate()
        self.assertFalse(report["local_checks_passed"])
        self.assertEqual(report["results"][1]["reason"], "NONFINITE_JSON_NUMBER")

    def test_unhashable_policy_type_returns_structured_failure(self):
        self.policy["requirements"][0]["type"] = ["file_exists"]
        self.pin = self.save()
        self.assertEqual(self.run_gate()["errors"], ["UNSUPPORTED_REQUIREMENT"])

    def test_oversized_policy_is_rejected_before_json_parsing(self):
        self.save()
        self.path.write_bytes(b"x" * (64 * 1024 + 20))
        self.pin = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertEqual(self.run_gate()["errors"], ["POLICY_TOO_LARGE"])

if __name__ == "__main__":
    unittest.main()
