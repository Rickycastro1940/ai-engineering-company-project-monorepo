from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.app import app  # noqa: E402
import agent  # noqa: E402
import inventory  # noqa: E402


class ErrorHandlingAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=REPO_ROOT)
        self.temp_path = Path(self.temp_dir.name)
        self.original_products_file = inventory.PRODUCTS_FILE
        inventory.PRODUCTS_FILE = self.temp_path / "products.csv"
        inventory.PRODUCTS_FILE.write_text(
            "product_id,name,quantity,unit\n1,Tomatoes,25,kg\n",
            encoding="utf-8",
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        inventory.PRODUCTS_FILE = self.original_products_file
        self.temp_dir.cleanup()

    def _repo_relative(self, path: Path) -> str:
        return path.relative_to(REPO_ROOT).as_posix()

    def test_incident_api_rejects_paths_outside_repo(self) -> None:
        response = self.client.post(
            "/api/incidents/analyze/summary",
            json={"input_file": "../outside.csv", "output_file": "results.csv"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Path must stay inside the repository")

    def test_incident_api_returns_bad_request_for_malformed_csv(self) -> None:
        bad_csv = self.temp_path / "bad.csv"
        bad_csv.write_text("incident_id,date\nBRS-1,2026-06-01\n", encoding="utf-8")

        response = self.client.post(
            "/api/incidents/analyze/summary",
            json={
                "input_file": self._repo_relative(bad_csv),
                "output_file": self._repo_relative(self.temp_path / "out.csv"),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("CSV is missing required columns", response.json()["detail"])

    def test_inventory_reports_corrupt_storage_and_rejects_blank_payloads(self) -> None:
        inventory.PRODUCTS_FILE.write_text(
            "product_id,name,quantity,unit\nnot-an-id,Tomatoes,25,kg\n",
            encoding="utf-8",
        )
        corrupt_response = self.client.get("/inventory")
        self.assertEqual(corrupt_response.status_code, 500)
        self.assertEqual(corrupt_response.json()["detail"], "Invalid inventory data in products.csv")

        inventory.PRODUCTS_FILE.write_text("product_id,name,quantity,unit\n", encoding="utf-8")
        blank_response = self.client.post("/inventory", json={"name": "   ", "quantity": 1, "unit": "kg"})
        self.assertEqual(blank_response.status_code, 422)

    def test_agent_tool_validation_returns_tool_errors(self) -> None:
        missing_product_id = agent.execute_tool("update_stock", {"delta": 1})
        self.assertTrue(missing_product_id["error"])
        self.assertEqual(missing_product_id["detail"], "Missing required argument: product_id")

        blank_name = agent.execute_tool("add_product", {"name": " ", "quantity": 1, "unit": "kg"})
        self.assertTrue(blank_name["error"])
        self.assertEqual(blank_name["detail"], "Argument name must be a non-empty string")

        non_object = agent.execute_tool("list_inventory", [])
        self.assertTrue(non_object["error"])
        self.assertEqual(non_object["detail"], "Tool arguments must be a JSON object")

    def test_cli_missing_input_exits_with_clear_error(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/analyze.py", "missing.csv"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Analysis failed: input file not found:", result.stderr)


if __name__ == "__main__":
    unittest.main()
