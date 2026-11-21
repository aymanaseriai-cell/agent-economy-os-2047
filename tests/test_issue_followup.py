import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation"))
from issue_followup import build_reply, CONSENT, MARKER

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)


def inbound(text="How much does the integration cost?"):
    return {
        "action": "created",
        "issue": {
            "number": 33, "title": "[Service request] Agent CI review",
            "state": "open", "user": {"login": "external-buyer"},
            "body": "### Public automated follow-up consent\n\n- [X] " + CONSENT,
        },
        "comment": {"id": 201, "body": text, "user": {"login": "external-buyer"}}
    }


def past_bot_comment(body, days=2):
    return {"user": {"login": "github-actions[bot]"}, "body": body,
            "created_at": (NOW - timedelta(days=days)).isoformat()}


class FollowupTests(unittest.TestCase):
    def test_consented_price_query(self):
        msg = build_reply(inbound(), [], NOW)
        self.assertIn("USD 49", msg)
        self.assertIn(MARKER + ":201", msg)
        self.assertIn("not a contract", msg)

    def test_private_scope_refuses_public_secret_requests(self):
        msg = build_reply(inbound("I want a private repository demo, how?"), [], NOW)
        self.assertIn("do not post private source code", msg)
        self.assertNotIn("USD 49", msg)

    def test_withdrawn_or_missing_checkbox(self):
        a = inbound()
        a["issue"]["body"] = a["issue"]["body"].replace("[X]", "[ ]")
        self.assertIsNone(build_reply(a, [], NOW))
        a["issue"]["body"] = ""
        self.assertIsNone(build_reply(a, [], NOW))

    def test_only_original_requester_can_trigger(self):
        a = inbound()
        a["comment"]["user"]["login"] = "unrelated-user"
        self.assertIsNone(build_reply(a, [], NOW))

    def test_does_not_reply_to_draft_pr(self):
        a = inbound()
        a["issue"]["pull_request"] = {"url": "ignored"}
        self.assertIsNone(build_reply(a, [], NOW))

    def test_closed_issue_or_wrong_action_no_reply(self):
        a = inbound()
        a["issue"]["state"] = "closed"
        self.assertIsNone(build_reply(a, [], NOW))
        a["issue"]["state"] = "open"
        a["action"] = "edited"
        self.assertIsNone(build_reply(a, [], NOW))

    def test_no_reply_for_generic_non_question(self):
        self.assertIsNone(build_reply(inbound("Thanks, received."), [], NOW))

    def test_same_comment_deduplicated(self):
        comments = [past_bot_comment(MARKER + ":201 -->\n prior reply")]
        self.assertIsNone(build_reply(inbound(), comments, NOW))

    def test_rate_limit_twenty_four_hours(self):
        comments = [past_bot_comment(MARKER + ":100 -->", days=0.5)]
        self.assertIsNone(build_reply(inbound(), comments, NOW))

    def test_total_reply_cap(self):
        comments = [past_bot_comment(MARKER + ":100 -->"),
                    past_bot_comment(MARKER + ":101 -->")]
        self.assertIsNone(build_reply(inbound(), comments, NOW))

    def test_unknown_pagination_fails_closed(self):
        self.assertIsNone(build_reply(inbound(), [{}] * 100, NOW))

    def test_valid_documentation_question(self):
        self.assertIn("buyer-controlled GitHub CI",
                      build_reply(inbound("Does the CI integration have a demo?"), [], NOW))


if __name__ == "__main__":
    unittest.main()
