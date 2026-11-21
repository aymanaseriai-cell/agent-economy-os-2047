"""Offline tests: prevent payment calls, arbitrary network targets, and false PASS."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError

from automation.agent_buyer_smoke import CHECKS, NoRedirect, inspect_target, run


class FakeResponse:
    def __init__(self, data=None, status=200, content_type="application/json"):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.raw = json.dumps(data if data is not None else {"ok": True}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, count):
        return self.raw[:count]


class FakeOpener:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.full_url, request.method, dict(request.headers), timeout))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result if self.result is not None else FakeResponse()


class DiscoverySmokeTests(unittest.TestCase):
    def test_only_free_urls_and_get_without_payment_headers(self):
        self.assertEqual(len(CHECKS), 5)
        for service_id, key, url in CHECKS:
            with self.subTest(service_id=service_id, key=key):
                self.assertTrue(url.startswith("https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/"))
                self.assertNotIn("/report", url)
                self.assertNotIn("/receipt", url.rsplit("/api/v1/", 1)[-1] if "/api/v1/" in url else "")
                fixture = ({"skills": [], "supportedInterfaces": []} if key == "offer_card"
                           else {"contract": {}, "contract_id": "abc", "sample_submission": {}} if service_id == "work_covenant_free"
                           else {"ok": True})
                opener = FakeOpener(FakeResponse(fixture))
                result = inspect_target({"id": service_id, key: url}, key, url, opener)
                self.assertEqual(result["status"], "REACHABLE_DEMO_ONLY")
                requested_url, method, headers, timeout = opener.calls[0]
                self.assertEqual(requested_url, url)
                self.assertEqual(method, "GET")
                self.assertEqual(timeout, 8)
                self.assertFalse(any("payment" in h.lower() or "authorization" in h.lower() for h in headers))

    def test_host_substitution_is_blocked_before_network(self):
        key, url = CHECKS[0][1], CHECKS[0][2]
        for changed in (url.replace("supabase.co", "supabase.co.attacker.example"),
                        url + "?tx=unsafe", url + "#anchor", "http:" + url[6:]):
            opener = FakeOpener()
            result = inspect_target({"id": CHECKS[0][0], key: changed}, key, url, opener)
            self.assertEqual(result["reason"], "catalog_url_not_exactly_allowlisted")
            self.assertEqual(opener.calls, [])

    def test_http_errors_are_not_sales_or_success(self):
        _, key, url = CHECKS[0]
        err = HTTPError(url, 302, "redirect", {}, None)
        result = inspect_target({"id": CHECKS[0][0], key: url}, key, url, FakeOpener(err))
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["http_status"], 302)
        self.assertFalse(result["payment_attempted"])
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.example/"))

    def test_bad_json_is_unverified(self):
        _, key, url = CHECKS[0]
        opener = FakeOpener(FakeResponse({"error": "fake"}))
        result = inspect_target({"id": CHECKS[0][0], key: url}, key, url, opener)
        self.assertEqual(result["reason"], "unexpected_json_shape")
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_complete_catalog_failure_does_not_claim_revenue(self):
        catalog = Path(__file__).resolve().parents[1] / "docs" / "agent-services.json"
        result = run(catalog, opener=FakeOpener(FakeResponse({"error": "unavailable"})))
        self.assertFalse(result["ok"])
        self.assertEqual(result["paid_requests_attempted"], 0)
        self.assertIs(result["commercial_revenue_verified"], False)
        self.assertTrue(all(x["status"] == "UNVERIFIED" for x in result["checks"]))

    def test_catalog_with_redirected_target_fails_closed(self):
        catalog = Path(__file__).resolve().parents[1] / "docs" / "agent-services.json"
        data = json.loads(catalog.read_text())
        data["services"][0]["demo"] = "https://redirect.example/"
        with TemporaryDirectory() as temp:
            file = Path(temp) / "catalog.json"
            file.write_text(json.dumps(data))
            opener = FakeOpener()
            result = run(file, opener=opener)
            self.assertFalse(result["ok"])
            self.assertEqual(result["checks"][0]["reason"], "catalog_url_not_exactly_allowlisted")
            self.assertEqual(len(opener.calls), 4)


if __name__ == "__main__":
    unittest.main()
