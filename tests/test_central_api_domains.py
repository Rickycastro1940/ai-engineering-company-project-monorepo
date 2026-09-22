from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.app import app  # pylint: disable=wrong-import-position

users = importlib.import_module("users")


class CentralApiDomainsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = users.DATABASE_PATH
        users.DATABASE_PATH = Path(self.temp_dir.name) / "company_api.db"
        self.client = TestClient(app)

    def tearDown(self) -> None:
        users.DATABASE_PATH = self.original_database_path
        self.temp_dir.cleanup()

    def _headers(self) -> dict[str, str]:
        created = self.client.post(
            "/users",
            json={"email": "ops@brasaland.test", "password": "secret-password"},
        )
        self.assertEqual(created.status_code, 201)
        token = self.client.post(
            "/auth/token",
            data={"username": "ops@brasaland.test", "password": "secret-password"},
        )
        self.assertEqual(token.status_code, 200)
        return {"Authorization": f"Bearer {token.json()['access_token']}"}

    def test_openapi_covers_technology_nouns(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]
        joined = " ".join(paths)
        for needle in ("/locations", "/menus", "/sales", "/customers", "/suppliers", "/inventory"):
            self.assertIn(needle, joined)

    def test_menus_are_public_and_priced_in_cop_and_usd(self) -> None:
        response = self.client.get("/menus")
        self.assertEqual(response.status_code, 200)
        items = response.json()
        self.assertGreaterEqual(len(items), 6)
        ids = {item["id"] for item in items}
        self.assertIn("grilled-sirloin", ids)
        for item in items:
            self.assertIn("Colombia", item["available_in"])
            self.assertIn("Florida", item["available_in"])
            self.assertGreater(item["price_cop"], 0)
            self.assertGreater(item["price_usd"], 0)

        catalogue = self.client.get("/menus/catalogue")
        self.assertEqual(catalogue.status_code, 200)
        self.assertEqual(catalogue.json()["currencies"], ["COP", "USD"])
        self.assertTrue(catalogue.json()["same_recipes_every_kitchen"])
        self.assertEqual(catalogue.json()["location_count"], 14)

        missing = self.client.get("/menus/not-a-dish")
        self.assertEqual(missing.status_code, 404)

    def test_sales_require_jwt_and_cover_fourteen_locations_both_currencies(self) -> None:
        anonymous = self.client.get("/sales/overview")
        self.assertEqual(anonymous.status_code, 401)

        headers = self._headers()
        overview = self.client.get("/sales/overview", headers=headers)
        self.assertEqual(overview.status_code, 200)
        payload = overview.json()
        self.assertEqual(payload["total_locations"], 14)
        self.assertEqual(payload["currencies"], ["COP", "USD"])
        self.assertGreater(payload["chain_total_cop"], 0)
        self.assertGreater(payload["chain_total_usd"], 0)
        self.assertGreater(payload["colombia_total_cop"], 0)
        self.assertGreater(payload["florida_total_usd"], 0)
        self.assertEqual(len(payload["locations"]), 14)
        currencies = {row["currency"] for row in payload["locations"]}
        self.assertEqual(currencies, {"COP", "USD"})

        brickell = self.client.get("/sales/us-mia-brickell", headers=headers)
        self.assertEqual(brickell.status_code, 200)
        self.assertEqual(brickell.json()["currency"], "USD")

        missing = self.client.get("/sales/no-such-site", headers=headers)
        self.assertEqual(missing.status_code, 404)

        alerts = self.client.get("/sales/alerts", headers=headers)
        self.assertEqual(alerts.status_code, 200)
        self.assertIsInstance(alerts.json(), list)

    def test_customers_require_jwt_and_keep_brasa_points_physical(self) -> None:
        self.assertEqual(self.client.get("/customers").status_code, 401)
        headers = self._headers()
        overview = self.client.get("/customers/overview", headers=headers)
        self.assertEqual(overview.status_code, 200)
        payload = overview.json()
        self.assertGreaterEqual(payload["total_customers"], 8)
        self.assertGreater(payload["colombia_count"], 0)
        self.assertGreater(payload["florida_count"], 0)
        self.assertFalse(payload["digital_loyalty"])
        self.assertEqual(payload["stamp_card_users"] + payload["unused_stamp_cards"], payload["total_customers"])

        one = self.client.get("/customers/cus-001", headers=headers)
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["loyalty_program"], "Brasa Points")
        self.assertEqual(one.json()["loyalty_medium"], "physical_stamp_card")
        self.assertFalse(one.json()["digital_loyalty"])
        self.assertTrue(one.json()["order_history"])

        missing = self.client.get("/customers/cus-999", headers=headers)
        self.assertEqual(missing.status_code, 404)

    def test_suppliers_require_jwt_and_cover_twenty_across_two_markets(self) -> None:
        self.assertEqual(self.client.get("/suppliers").status_code, 401)
        headers = self._headers()
        overview = self.client.get("/suppliers/overview", headers=headers)
        self.assertEqual(overview.status_code, 200)
        payload = overview.json()
        self.assertEqual(payload["total_suppliers"], 20)
        self.assertEqual(payload["colombia_count"] + payload["florida_count"], 20)
        self.assertGreater(payload["price_alerts"], 0)

        colombia = self.client.get("/suppliers", headers=headers, params={"country": "Colombia"})
        self.assertEqual(colombia.status_code, 200)
        self.assertEqual(len(colombia.json()), 10)
        self.assertTrue(all(row["country"] == "Colombia" for row in colombia.json()))

        proteins = self.client.get("/suppliers", headers=headers, params={"category": "proteins"})
        self.assertEqual(proteins.status_code, 200)
        self.assertGreaterEqual(len(proteins.json()), 2)

        one = self.client.get("/suppliers/sup-013", headers=headers)
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["name"], "Gulf Coast Produce")
        self.assertEqual(len(one.json()["price_history"]), 2)

        missing = self.client.get("/suppliers/sup-999", headers=headers)
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
