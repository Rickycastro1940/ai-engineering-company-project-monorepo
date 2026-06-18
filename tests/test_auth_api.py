from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ["AUTH_USERS_FILE"] = str(Path(tempfile.mkdtemp(prefix="auth-api-test-")) / "users.json")
os.environ["AUTH_JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from api.app import app  # noqa: E402


class AuthApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.email = "owner@example.com"
        self.password = "correct-password"

    def test_auth_flow_and_protected_inventory(self) -> None:
        unauthorized = self.client.get("/inventory")
        self.assertEqual(unauthorized.status_code, 401)

        registered = self.client.post(
            "/auth/register",
            json={"name": "Ops Owner", "email": self.email, "password": self.password},
        )
        self.assertEqual(registered.status_code, 201)
        token = registered.json()["token"]
        user_id = registered.json()["user"]["id"]
        self.assertEqual(registered.json()["user"]["email"], self.email)

        headers = {"Authorization": f"Bearer {token}"}
        inventory = self.client.get("/inventory", headers=headers)
        self.assertEqual(inventory.status_code, 200)
        self.assertGreaterEqual(len(inventory.json()), 1)

        updated_profile = self.client.put(f"/users/{user_id}", headers=headers, json={"name": "Operations Lead"})
        self.assertEqual(updated_profile.status_code, 200)
        self.assertEqual(updated_profile.json()["name"], "Operations Lead")

        changed_password = self.client.post(
            "/auth/change-password",
            headers=headers,
            json={"current_password": self.password, "new_password": "new-correct-password"},
        )
        self.assertEqual(changed_password.status_code, 204)

        old_login = self.client.post("/auth/login", json={"email": self.email, "password": self.password})
        self.assertEqual(old_login.status_code, 401)

        new_login = self.client.post("/auth/login", json={"email": self.email, "password": "new-correct-password"})
        self.assertEqual(new_login.status_code, 200)
        self.assertIn("token", new_login.json())


if __name__ == "__main__":
    unittest.main()
