from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.app import app  # pylint: disable=wrong-import-position


class InventoryErrorHandlingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_missing_product_returns_404(self) -> None:
        response = self.client.patch("/inventory/999999", json={"delta": 1})
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_negative_alert_threshold_returns_400(self) -> None:
        response = self.client.get("/inventory/alerts", params={"threshold": -1})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
