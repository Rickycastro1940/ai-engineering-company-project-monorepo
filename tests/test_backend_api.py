from __future__ import annotations

import csv
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

inventory = importlib.import_module("inventory")


class BackendApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.products_file = Path(self.temp_dir.name) / "products.csv"
        self._write_products(
            [
                {"product_id": 1, "name": "Tomatoes", "quantity": 25, "unit": "kg"},
                {"product_id": 2, "name": "Mozzarella", "quantity": 8, "unit": "kg"},
                {"product_id": 3, "name": "Napkins", "quantity": 120, "unit": "boxes"},
            ]
        )
        self.original_products_file = inventory.PRODUCTS_FILE
        inventory.PRODUCTS_FILE = self.products_file
        self.client = TestClient(app)

    def tearDown(self) -> None:
        inventory.PRODUCTS_FILE = self.original_products_file
        self.temp_dir.cleanup()

    def _write_products(self, rows: list[dict[str, str | int]]) -> None:
        with self.products_file.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=inventory.FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    def test_health_and_status_endpoints(self) -> None:
        health_response = self.client.get("/health")
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json(), {"status": "ok"})

        status_response = self.client.get("/api/status")
        self.assertEqual(status_response.status_code, 200)
        payload = status_response.json()
        self.assertEqual(payload["service"], "company-backend-api")
        self.assertEqual(payload["status"], "ok")
        self.assertIn("inventory-summary", payload["capabilities"])

    def test_inventory_summary_aggregates_current_stock(self) -> None:
        response = self.client.get("/inventory/summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "product_count": 3,
                "total_quantity_by_unit": {"boxes": 120, "kg": 33},
                "low_stock_count": 1,
                "low_stock_threshold": 10,
            },
        )

    def test_inventory_summary_rejects_negative_threshold(self) -> None:
        response = self.client.get("/inventory/summary?threshold=-1")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Threshold must be greater than or equal to 0")

    def test_read_and_delete_inventory_item(self) -> None:
        read_response = self.client.get("/inventory/2")
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["name"], "Mozzarella")

        delete_response = self.client.delete("/inventory/2")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["product_id"], 2)

        missing_response = self.client.get("/inventory/2")
        self.assertEqual(missing_response.status_code, 404)

        list_response = self.client.get("/inventory")
        remaining_ids = [product["product_id"] for product in list_response.json()]
        self.assertEqual(remaining_ids, [1, 3])


if __name__ == "__main__":
    unittest.main()
