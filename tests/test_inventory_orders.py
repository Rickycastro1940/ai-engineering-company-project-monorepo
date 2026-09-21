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
        self.orders_file = Path(self.temp_dir.name) / "inventory_orders.csv"
        self.orders_patcher = patch.object(inventory, "ORDERS_FILE", self.orders_file)
        self.orders_patcher.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.orders_patcher.stop()
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


class OutboundOrderApiTests(unittest.TestCase):
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
        self.orders_file = Path(self.temp_dir.name) / "inventory_orders.csv"
        self.orders_patcher = patch.object(inventory, "ORDERS_FILE", self.orders_file)
        self.orders_patcher.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.orders_patcher.stop()
        self.file_patcher.stop()
        users.DATABASE_PATH = self.original_database_path
        self.temp_dir.cleanup()

    def _auth_headers(self, email: str = "ops-out@brasaland.test") -> dict[str, str]:
        self.client.post("/users", json={"email": email, "password": "secret-password"})
        token = self.client.post(
            "/auth/login",
            json={"email": email, "password": "secret-password"},
        ).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_outbound_order_requires_bearer_token(self) -> None:
        response = self.client.post(
            "/inventory/orders/outbound",
            json={"product_id": 2, "quantity": 1},
        )
        self.assertEqual(response.status_code, 401)

    def test_product_current_stock_is_returned(self) -> None:
        listed = self.client.get("/inventory")
        self.assertEqual(listed.status_code, 200)
        mozzarella = next(item for item in listed.json() if item["name"] == "Mozzarella")
        self.assertEqual(mozzarella["current_stock"], 8)
        self.assertEqual(mozzarella["quantity"], 8)

        response = self.client.get("/inventory/2")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["name"], "Mozzarella")
        self.assertEqual(body["current_stock"], 8)
        self.assertEqual(body["quantity"], 8)

    def test_outbound_order_reduces_on_hand_stock(self) -> None:
        response = self.client.post(
            "/inventory/orders/outbound",
            json={"product_id": 2, "quantity": 3},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["order_type"], "outbound")
        self.assertEqual(body["product"]["current_stock"], 5)

    def test_outbound_order_insufficient_stock_is_400(self) -> None:
        response = self.client.post(
            "/inventory/orders/outbound",
            json={"product_id": 2, "quantity": 999},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("insufficient stock", body["message"].lower())


class InventoryOrdersHistoryApiTests(unittest.TestCase):
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
        self.orders_file = Path(self.temp_dir.name) / "inventory_orders.csv"
        self.orders_patcher = patch.object(inventory, "ORDERS_FILE", self.orders_file)
        self.orders_patcher.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.orders_patcher.stop()
        self.file_patcher.stop()
        users.DATABASE_PATH = self.original_database_path
        self.temp_dir.cleanup()

    def _auth_headers(self, email: str = "ops-history@brasaland.test") -> dict[str, str]:
        self.client.post("/users", json={"email": email, "password": "secret-password"})
        token = self.client.post(
            "/auth/login",
            json={"email": email, "password": "secret-password"},
        ).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_list_orders_requires_bearer_token(self) -> None:
        response = self.client.get("/inventory/orders")
        self.assertEqual(response.status_code, 401)

    def test_list_orders_is_empty_before_any_movement(self) -> None:
        response = self.client.get("/inventory/orders", headers=self._auth_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_list_orders_returns_inbound_and_outbound_newest_first(self) -> None:
        headers = self._auth_headers()
        inbound = self.client.post(
            "/inventory/orders/inbound",
            json={"product_id": 1, "quantity": 4},
            headers=headers,
        )
        outbound = self.client.post(
            "/inventory/orders/outbound",
            json={"product_id": 2, "quantity": 2},
            headers=headers,
        )
        self.assertEqual(inbound.status_code, 201)
        self.assertEqual(outbound.status_code, 201)

        listed = self.client.get("/inventory/orders", headers=headers)
        self.assertEqual(listed.status_code, 200)
        rows = listed.json()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["order_type"], "outbound")
        self.assertEqual(rows[0]["product_name"], "Mozzarella")
        self.assertEqual(rows[0]["quantity"], 2)
        self.assertEqual(rows[1]["order_type"], "inbound")
        self.assertEqual(rows[1]["product_name"], "Tomatoes")
        self.assertEqual(rows[1]["quantity"], 4)
        for row in rows:
            self.assertIn("created_at", row)
            self.assertTrue(row["created_at"])
            self.assertIn("user_uuid", row)
            self.assertEqual(len(row["user_uuid"]), 36)
            self.assertNotIn("delete", row)
            self.assertNotIn("edit", row)

