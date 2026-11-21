#!/usr/bin/env python3
import unittest
from automation.opportunity_scan import evaluate

class RadarTests(unittest.TestCase):
    def issue(self, title, body=""):
        return {"html_url":"https://github.com/example/project/issues/12", "title":title, "state":"open", "body":body}
    def test_buyer_signal_is_not_verified_purchase(self):
        x=evaluate(self.issue("Looking for paid AI agent workflow evidence audit","Budget request for an independent reviewer"))
        self.assertEqual(x["tier"],"manual_buyer_intent_review")
        self.assertFalse(x["buying_authority_verified"])
        self.assertFalse(x["funded_opportunity_verified"])
        self.assertFalse(x["permission_to_contact_verified"])
    def test_vendor_not_a_buyer(self):
        x=evaluate(self.issue("I built an agent evidence audit tool", "Check out my service"))
        self.assertEqual(x["tier"],"research_only")
    def test_unsafe_url_rejected(self):
        x=self.issue("Need evidence audit");x["html_url"]="https://evil.test/request"
        self.assertIsNone(evaluate(x))
    def test_closed_issue_rejected(self):
        x=self.issue("Need agent workflow audit"); x["state"]="closed"
        self.assertIsNone(evaluate(x))
    def test_pr_rejected(self):
        x=self.issue("Need agent evidence audit"); x["pull_request"]={"url":"https://api.github.com/foo"}
        self.assertIsNone(evaluate(x))

if __name__=="__main__":
    unittest.main()
