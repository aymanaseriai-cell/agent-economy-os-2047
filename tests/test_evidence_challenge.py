import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation"))
from evidence_challenge import CONSENT, SCENARIOS, build_evidence_response, load_verified_case
from issue_router import build_response

def make_issue(choice, step="Show me the free synthetic demonstration only", checked=True, context=""):
    return {"title": "[Evidence challenge] " + choice, "body":
            "### Evidence failure to explore\n\n" + choice +
            "\n\n### Preferred next step\n\n" + step +
            "\n\n### Optional public context\n\n" + context +
            "\n\n### Public-only permission\n\n- [" + ("X" if checked else " ") + "] " + CONSENT}

class ChallengeTests(unittest.TestCase):
    def test_all_five_recomputed(self):
        for name, (case_id, _, _) in SCENARIOS.items():
            with self.subTest(case=case_id):
                result = build_response(make_issue(name))
                self.assertIn(case_id, result)
                self.assertIn("UNVERIFIED_SOURCE_FRESHNESS", result)
                self.assertIn("version-pinned", result)
    def test_missing_consent_fails_closed(self):
        self.assertIsNone(build_response(make_issue(next(iter(SCENARIOS)), checked=False)))
    def test_unknown_choice_fails_closed(self):
        self.assertIsNone(build_response(make_issue("Attempt a real payment")))
    def test_unknown_next_step_fails_closed(self):
        self.assertIsNone(build_response(make_issue(next(iter(SCENARIOS)),step="Transfer money")))
    def test_private_context_not_duplicated(self):
        body = build_response(make_issue(next(iter(SCENARIOS)), context="DO_NOT_REPEAT_SECRET_12345"))
        self.assertNotIn("DO_NOT_REPEAT_SECRET_12345", body)
    def test_opted_in_business_case_nonbinding(self):
        x = build_response(make_issue(next(iter(SCENARIOS)), step="Explore a scoped enterprise pilot (no payment)"))
        self.assertIn("USD $750", x)
        self.assertIn("non-binding", x)
    def test_corrupt_fixture_fails_closed(self):
        path = Path(__file__).resolve().parents[1] / "fixtures" / "handoff-claims-v1" / "handoff_claims_v1_1.json"
        fixture = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
        fixture["cases"][0]["expected"]["saved_integrity"] = "FAIL"
        with self.assertRaisesRegex(ValueError,"mismatch"):
            load_verified_case("baseline",fixture)
    def test_unrelated_issues_not_replied(self):
        self.assertIsNone(build_evidence_response({"title":"Hello","body":"text"}))
        self.assertIsNone(build_response({"title":"Hello","body":"text"}))

if __name__=="__main__":
    unittest.main()
