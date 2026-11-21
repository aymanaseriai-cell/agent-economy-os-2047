import unittest
from examples.work_covenant_live_quickstart import check

class WorkCovenantLiveQuickstartTests(unittest.TestCase):
    def make_client(self, *, negative_passes=False, fake_buyer=False):
        calls = []
        demo = {"ok": True, "contract": {"criteria": []}, "contract_id": "demo123",
                "sample_submission": {"artifacts": [{"name": "report.json", "content": '{"ok":true}'}]}}
        def client(path, payload=None):
            calls.append((path, payload))
            if path == "/demo":
                return demo
            if len(calls) not in (2, 3):
                raise AssertionError("Unexpected evaluation call")
            negative = len(calls) == 3
            return {"status": "local_checks_passed" if not negative or negative_passes
                    else "local_checks_failed",
                    "contract_id": "demo123",
                    "results": [{"id": "status_ok", "pass": not negative or negative_passes}],
                    "buyer_acceptance_verified": fake_buyer,
                    "payment_verified": False, "onchain_settlement_verified": False}
        return client, calls

    def test_happy_and_tampered_cases(self):
        client, calls = self.make_client()
        result = check(client)
        self.assertEqual(result["tampered_negative"], "local_checks_failed")
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1][1]["submission"]["artifacts"][0]["content"], '{"ok":true}')
        self.assertEqual(calls[2][1]["submission"]["artifacts"][0]["content"], '{"ok":false}')
        self.assertFalse(result["customer_adoption_verified"])

    def test_fail_closed_if_tampering_passes(self):
        client, _ = self.make_client(negative_passes=True)
        with self.assertRaisesRegex(RuntimeError, "Tampered output passed"):
            check(client)

    def test_fail_closed_on_fake_buyer_approval(self):
        client, _ = self.make_client(fake_buyer=True)
        with self.assertRaisesRegex(RuntimeError, "unsupported buyer_acceptance_verified"):
            check(client)

if __name__ == "__main__":
    unittest.main()
