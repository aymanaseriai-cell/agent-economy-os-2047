"""Fail-closed checks for the public machine-readable agent-buyer catalog."""
import json
import unittest
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "agent-services.json"

class AgentServiceCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(
            CATALOG.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
            object_pairs_hook=cls.reject_duplicate_keys
        )

    @staticmethod
    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key in catalog: " + key)
            result[key] = value
        return result

    def test_catalog_is_explicitly_non_authorizing(self):
        self.assertEqual(self.catalog["schema"], "agent-economy.service-catalog.v1")
        self.assertIs(self.catalog["autonomous_purchase"], False)
        self.assertIs(self.catalog["owner_approval_required_for_paid_calls"], True)
        self.assertIs(self.catalog["independently_verified_organic_buyers"], False)
        self.assertIs(self.catalog["independently_verified_commercial_revenue"], False)

    def test_service_identifiers_and_free_paid_distinction(self):
        services = self.catalog["services"]
        ids = [service["id"] for service in services]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {
            "work_covenant_free", "base_usdc_receipt_lite",
            "base_usdc_receipt", "automated_assessment_750"
        })
        self.assertEqual(sum(s["billing"] == "free" for s in services), 1)
        for service in services:
            if service["billing"] == "free":
                self.assertNotIn("price", service)
                self.assertEqual(service["method"], "POST")
                continue
            self.assertEqual(service["billing"], "x402-v2")
            self.assertIs(service["buyer_owner_authorization_required"], True)
            self.assertIs(service["verified_organic_buyer"], False)
            self.assertEqual(service["price"]["currency"], "USDC")
            self.assertEqual(service["price"]["network"], "eip155:8453")
            try:
                self.assertGreater(Decimal(service["price"]["amount"]), 0)
            except InvalidOperation:
                self.fail("invalid decimal price")

    def test_prices_match_documented_service_routes(self):
        prices = {s["id"]: s.get("price", {}).get("amount") for s in self.catalog["services"]}
        self.assertEqual(prices["base_usdc_receipt_lite"], "0.005")
        self.assertEqual(prices["base_usdc_receipt"], "0.01")
        self.assertEqual(prices["automated_assessment_750"], "750.00")
        human = self.catalog["human_scoped_pilot"]
        self.assertEqual((human["currency"], human["indicative_amount"]), ("USD", "750"))
        self.assertIs(human["binding_quote"], False)
        self.assertIs(human["payment_enabled"], False)

    def test_starter_49_clear_scope_and_not_a_checkout(self):
        pilot = self.catalog["human_scoped_starter_pilot"]
        self.assertEqual((pilot["currency"], pilot["indicative_amount"]), ("USD", "49"))
        self.assertIs(pilot["binding_quote"], False)
        self.assertIs(pilot["payment_enabled"], False)
        self.assertIn("up to five artifact", pilot["scope"])
        self.assertIn("public or synthetic", pilot["scope"])
        self.assertNotEqual(pilot["indicative_amount"], self.catalog["human_scoped_pilot"]["indicative_amount"])
        scope = (ROOT / "docs" / "PILOT_49.md").read_text(encoding="utf-8")
        template = (ROOT / ".github" / "ISSUE_TEMPLATE" / "service-request.yml").read_text(encoding="utf-8")
        website = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for text in (scope, template, website, readme):
            self.assertIn("49", text)
        self.assertIn("buyer-pinned output evidence", template)
        self.assertIn("up to five artifacts", scope)
        self.assertIn("non-binding", scope)
        self.assertIn("docs/PILOT_49.md", website)
        self.assertIn("docs/PILOT_49.md", readme)
        self.assertIn("human_scoped_pilot", self.catalog)

    def test_only_explicit_https_endpoints(self):
        def urls(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ("endpoint", "demo", "openapi", "documentation", "form", "card_url", "offer_card", "free_preflight", "sample_report") and isinstance(value, str):
                        yield value
                    else:
                        yield from urls(value)
            elif isinstance(obj, list):
                for value in obj:
                    yield from urls(value)
        links = list(urls(self.catalog))
        self.assertGreaterEqual(len(links), 9)
        for link in links:
            with self.subTest(link=link):
                parsed = urlparse(link)
                self.assertEqual(parsed.scheme, "https")
                self.assertTrue(parsed.netloc)
                self.assertIsNone(parsed.username)
                self.assertIsNone(parsed.password)

    def test_discovery_files_and_site_links_present(self):
        guide = (ROOT / "docs" / "llms.txt").read_text(encoding="utf-8")
        website = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("agent-services.json", guide)
        self.assertIn('href="./agent-services.json"', website)
        self.assertIn('href="./llms.txt"', website)
        self.assertIn("docs/agent-services.json", readme)
        self.assertIn("owner authorizes", website)

if __name__ == "__main__":
    unittest.main()
