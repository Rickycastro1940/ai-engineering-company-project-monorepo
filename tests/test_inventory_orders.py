from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.app import app  # pylint: disable=wrong-import-position

users = importlib.import_module("users")
inventory = importlib.import_module("inventory")


class InboundOrderApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = users.DATABASE_PATH
        users.DATABASE_PATH = Path(self.temp_dir.name) / "company_api.db"
        self.products_file = Path(self.temp_dir.name) / "products.csv"
        self.products_file.write_text(
            "product_id,name,quantity,unit\n1,Tomatoes,25,kg\n2,Mozzarella,8,kg\n",
            encoding="utf-8",
        )
        self.file_patcher = patch.object(inventory, "PRODUCTS_FILE", self.products_file)
        self.file_patcher.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.file_patcher.stop()
        users.DATABASE_PATH = self.original_database_path
        self.temp_dir.cleanup()

    def _auth_headers(self, email: str = "ops@brasaland.test") -> dict[str, str]:
        self.client.post("/users", json={"email": email, "password": "secret-password"})
        token = self.client.post(
            "/auth/login",
            json={"email": email, "password": "secret-password"},
        ).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_inbound_order_requires_bearer_token(self) -> None:
        response = self.client.post(
            "/inventory/orders/inbound",
            json={"product_id": 1, "quantity": 3},
        )
        self.assertEqual(response.status_code, 401)

    def test_inbound_order_adds_on_hand_stock(self) -> None:
        response = self.client.post(
            "/inventory/orders/inbound",
            json={"product_id": 1, "quantity": 3},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["order_type"], "inbound")
        self.assertEqual(body["quantity"], 3)
        self.assertEqual(body["product"]["name"], "Tomatoes")
        self.assertEqual(body["product"]["quantity"], 28)

    def test_inbound_order_unknown_product_is_404(self) -> None:
        response = self.client.post(
            "/inventory/orders/inbound",
            json={"product_id": 999, "quantity": 1},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertIn("not found", body["message"].lower())

    def test_inbound_order_zero_quantity_is_422(self) -> None:
        response = self.client.post(
            "/inventory/orders/inbound",
            json={"product_id": 1, "quantity": 0},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 422)
