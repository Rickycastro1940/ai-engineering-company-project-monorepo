"""Centralized incident manager: seed transforms, lifecycle, and HTTP errors."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
API_DIR = REPO_ROOT / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from packages.shared.incident_rules import transform_csv_row, validate_record  # noqa: E402
from incident_store import seed_csv, summary  # noqa: E402

CSV_PATH = REPO_ROOT / "scripts" / "incidents-brasaland.csv"


class SeedTransformTests(unittest.TestCase):
    def test_official_csv_maps_to_expected_totals(self) -> None:
        import csv

        valid = 0
        invalid = 0
        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}
        with CSV_PATH.open(newline="", encoding="utf-8") as handle:
            for record in csv.DictReader(handle):
                if not validate_record(record).is_valid:
                    invalid += 1
                    continue
                mapped = transform_csv_row(record)
                self.assertIsNotNone(mapped)
                assert mapped is not None
                self.assertEqual(mapped["origin"], "customer")
                valid += 1
                by_status[mapped["status"]] = by_status.get(mapped["status"], 0) + 1
                by_category[mapped["category"]] = by_category.get(mapped["category"], 0) + 1
        self.assertEqual(valid, 96)
        self.assertEqual(invalid, 4)
        self.assertEqual(by_status, {"open": 32, "resolved": 50, "discarded": 14})
        self.assertEqual(
            by_category,
            {
                "customer_complaint": 48,
                "equipment_failure": 17,
                "supply_issue": 22,
                "staff_issue": 9,
            },
        )

    def test_seed_is_idempotent_and_skips_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "incidents.db"
            first = seed_csv(CSV_PATH, database)
            self.assertEqual(first.inserted, 96)
            self.assertEqual(len(first.invalid), 4)
            self.assertEqual(first.already_present, 0)
            second = seed_csv(CSV_PATH, database)
            self.assertEqual(second.inserted, 0)
            self.assertEqual(second.already_present, 96)
            os.environ["INCIDENTS_DATABASE_PATH"] = str(database)
            try:
                totals = summary()
            finally:
                os.environ.pop("INCIDENTS_DATABASE_PATH", None)
            self.assertEqual(totals["total"], 96)
            self.assertEqual(totals["by_status"]["open"], 32)
            self.assertEqual(totals["by_status"]["resolved"], 50)
            self.assertEqual(totals["by_status"]["discarded"], 14)
            self.assertEqual(totals["by_category"]["customer_complaint"], 48)
            self.assertEqual(totals["by_origin"]["customer"], 96)
            self.assertEqual(totals["by_status"]["in_progress"], 0)


class IncidentApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database = Path(self.tmp.name) / "incidents.db"
        os.environ["INCIDENTS_DATABASE_PATH"] = str(self.database)
        from api.app import app
        from fastapi.testclient import TestClient

        self.client = TestClient(app)

    def tearDown(self) -> None:
        os.environ.pop("INCIDENTS_DATABASE_PATH", None)
        self.tmp.cleanup()

    def _payload(self, **overrides: str) -> dict[str, str]:
        body = {
            "title": "Fryer will not hold temperature",
            "description": "The fryer at the line dropped below the recipe range during lunch.",
            "category": "equipment_failure",
            "status": "open",
            "origin": "branch",
            "branch": "medellin_centro",
        }
        body.update(overrides)
        return body

    def test_empty_database_returns_empty_list_and_zero_metrics(self) -> None:
        listing = self.client.get("/api/incidents")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json(), [])
        totals = self.client.get("/api/incidents/summary")
        self.assertEqual(totals.status_code, 200)
        body = totals.json()
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["by_status"]["open"], 0)
        self.assertEqual(body["by_branch"]["central"], 0)
        self.assertIn("facility_issue", body["by_category"])

    def test_create_validates_fields_and_lists_detail(self) -> None:
        missing = self.client.post("/api/incidents", json=self._payload(title="  "))
        self.assertEqual(missing.status_code, 400)
        body = missing.json()
        self.assertEqual(body["field"], "title")
        self.assertEqual(body["detail"]["errors"][0]["field"], "title")
        self.assertIn("title", body["message"].lower() + body["detail"]["message"].lower())
        self.assertNotIn("traceback", json.dumps(body).lower())

        created = self.client.post("/api/incidents", json=self._payload())
        self.assertEqual(created.status_code, 201)
        stored = created.json()
        self.assertTrue(stored["id"])
        self.assertNotIn("source_incident_id", stored)
        fetched = self.client.get(f"/api/incidents/{stored['id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["branch"], "medellin_centro")

        missing_row = self.client.get("/api/incidents/does-not-exist")
        self.assertEqual(missing_row.status_code, 404)
        self.assertNotIn("traceback", json.dumps(missing_row.json()).lower())

    def test_status_transitions_and_filters(self) -> None:
        created = self.client.post("/api/incidents", json=self._payload()).json()
        incident_id = created["id"]
        illegal = self.client.patch(f"/api/incidents/{incident_id}/status", json={"status": "resolved"})
        self.assertEqual(illegal.status_code, 400)
        self.assertEqual(illegal.json()["field"], "status")
        self.assertEqual(self.client.get(f"/api/incidents/{incident_id}").json()["status"], "open")

        moved = self.client.patch(f"/api/incidents/{incident_id}/status", json={"status": "in_progress"})
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(moved.json()["status"], "in_progress")
        closed = self.client.patch(f"/api/incidents/{incident_id}/status", json={"status": "resolved"})
        self.assertEqual(closed.status_code, 200)
        final = self.client.patch(f"/api/incidents/{incident_id}/status", json={"status": "open"})
        self.assertEqual(final.status_code, 400)

        self.client.post(
            "/api/incidents",
            json=self._payload(title="Late produce", category="supply_issue", origin="internal", branch="central"),
        )
        filtered = self.client.get("/api/incidents", params={"branch": "central", "origin": "internal"})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(len(filtered.json()), 1)
        self.assertEqual(filtered.json()[0]["category"], "supply_issue")

    def test_summary_after_seed_matches_context(self) -> None:
        seed_csv(CSV_PATH, self.database)
        body = self.client.get("/api/incidents/summary").json()
        self.assertEqual(body["by_status"]["open"], 32)
        self.assertEqual(body["by_status"]["resolved"], 50)
        self.assertEqual(body["by_status"]["discarded"], 14)
        self.assertEqual(body["by_category"]["customer_complaint"], 48)
        self.assertEqual(body["by_category"]["equipment_failure"], 17)
        self.assertEqual(body["by_category"]["supply_issue"], 22)
        self.assertEqual(body["by_category"]["staff_issue"], 9)
        self.assertEqual(body["total"], 96)

    def test_unhandled_exception_hides_traceback(self) -> None:
        from fastapi.testclient import TestClient
        from api.app import app
        import incidents

        client = TestClient(app, raise_server_exceptions=False)
        with patch.object(incidents.incident_store, "summary", side_effect=RuntimeError("secret db path /home/hidden")):
            response = client.get("/api/incidents/summary")
        self.assertEqual(response.status_code, 500)
        text = json.dumps(response.json()).lower()
        self.assertNotIn("traceback", text)
        self.assertNotIn("/home/hidden", text)
        self.assertIn("internal server error", text)


class SeedScriptTests(unittest.TestCase):
    def test_cli_reports_invalid_rows_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "incidents.db")
            command = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "seed_incidents.py"),
                str(CSV_PATH),
                "--database",
                database,
            ]
            first = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("Inserted: 96", first.stdout)
            self.assertIn("Invalid CSV rows (not inserted): 4", first.stdout)
            self.assertIn("Invalid records:", first.stdout)
            second = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("Inserted: 0", second.stdout)
            self.assertIn("Already present: 96", second.stdout)


if __name__ == "__main__":
    unittest.main()
