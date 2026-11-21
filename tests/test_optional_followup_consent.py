"""Regression guard: opt-in consent for automated public follow-up must be optional."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OptionalConsentFormTests(unittest.TestCase):
    def test_form_does_not_force_automated_followup_consent(self):
        text = (ROOT / ".github/ISSUE_TEMPLATE/service-request.yml").read_text(encoding="utf-8")
        self.assertEqual(text.count("id: automated-followup-consent"), 1)
        consent_section = text.split("id: automated-followup-consent", 1)[1]
        self.assertIn("I request automated replies to my follow-up comments", consent_section)
        self.assertIn("required: false", consent_section)
        self.assertNotIn("required: true", consent_section)


if __name__ == "__main__":
    unittest.main()
