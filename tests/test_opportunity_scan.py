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
    def test_strong_buyer_is_research_not_customer(self):
        x = evaluate(self.issue("Looking for paid AI agent workflow evidence audit",
                                "Budget request for an independent reviewer"))
        self.assertEqual(x["tier"], "manual_buyer_intent_review")
        self.assertFalse(x["buyer_intent_verified"])
        self.assertFalse(x["permission_to_contact_verified"])

    def test_internal_agent_feature_backlog_not_commercial_buyer(self):
        for title, body in (
            ("Add unit tests for web x402 client request and receipt helpers",
             "Acceptance criteria: write deterministic Bun tests for existing payment code."),
            ("[Frontend] Add client-side x402 payment receipt persistence",
             "Proposed implementation: session storage and tests for retry flow."),
            ("Feature: provider receipt webhooks after verified x402 payment",
             "Priority P2; failures retried with backoff and test coverage."),
        ):
            with self.subTest(title=title):
                x = evaluate(self.issue(title, body))
                self.assertEqual(x["tier"], "research_only")
                self.assertEqual(x["classification_reason"], "no_explicit_procurement_signal")

    def test_bot_sales_promotion_not_buyer(self):
        x = self.issue("Fleet compliance for OpenHands agent receipt audit",
                       "Buy (live): POST /v1/packages/buy. Our pricing and catalog.")
        x["user"] = {"login": "cursor[bot]"}
        r = evaluate(x)
        self.assertEqual(r["tier"], "research_only")
        self.assertTrue(r["bot_authored"])
        self.assertEqual(r["classification_reason"], "bot_authored")

    def test_real_public_rfp_is_unverified_review_only(self):
        x = evaluate(self.issue(
            "RFP: independent AI agent handoff evidence verification",
            "We are seeking a consultant for reproducible acceptance review."))
        self.assertEqual(x["tier"], "manual_buyer_intent_review")
        self.assertEqual(x["classification_reason"], "external_commercial_intent_needs_verification")
        self.assertFalse(x["buying_authority_verified"])
        self.assertFalse(x["funded_opportunity_verified"])

    def test_generic_request_without_budget_is_not_buyer(self):
        x = evaluate(self.issue("Need to implement a workflow receipt verifier",
                                "Please implement support for the callback next sprint."))
        self.assertEqual(x["tier"], "research_only")
        self.assertFalse(x["procurement_phrase_present"])

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
