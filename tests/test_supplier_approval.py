"""Supplier approval handoff: Supplier, Compliance (knowledge base), Operations."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.supplier_approval.orchestrator import review_supplier_application  # noqa: E402
from api.app import app  # noqa: E402

users = importlib.import_module("users")

COLOMBIA_PROTEIN = """
Legal name: Carnes Andinas
Country: Colombia
Categories: proteins
Emergency surcharge: 8%
Status: active
Health: INVIMA sanitary registration is on file for the Medellín plant.
"""

FLORIDA_PACKAGING = """
Legal name: Miami Boxes
Country: United States
Categories: packaging
"""

ZERO_RISK_SAUCE = """
Legal name: Salsa Limpia
Country: United States
Categories: sauces
Health: We guarantee zero cross-contamination risk on every bottle. FDA registered.
"""

HIGH_SURCHARGE = """
Legal name: Carnes del Rio
Country: Colombia
Categories: proteins
Emergency surcharge: 12%
Health: INVIMA registration on file.
"""


@pytest.fixture()
def client():
    temp_dir = tempfile.TemporaryDirectory()
    original_database_path = users.DATABASE_PATH
    users.DATABASE_PATH = Path(temp_dir.name) / "company_api.db"
    try:
        yield TestClient(app)
    finally:
        users.DATABASE_PATH = original_database_path
        temp_dir.cleanup()


def _headers(client: TestClient) -> dict[str, str]:
    created = client.post(
        "/auth/register",
        json={"email": "lucia.procurement@brasaland.test", "password": "secret-password"},
    )
    assert created.status_code == 201, created.text
    return {"Authorization": f"Bearer {created.json()['access_token']}"}


def _documents(result: dict) -> set[str]:
    return {item["source_document"] for item in result["compliance"]["sources"]}


def test_roles_run_in_order_and_approve_colombia_protein() -> None:
    result = review_supplier_application({"raw_text": COLOMBIA_PROTEIN})
    assert result["roles"] == ["supplier", "compliance", "operations"]
    assert result["orchestration"] == "plain-python-handoff"
    assert result["llm"] == "not_used"
    assert result["decision"] == "approve"
    assert result["market"] == "Colombia"
    assert result["currency"] == "COP"
    assert result["parsed"]["categories"] == ["proteins"]
    assert result["parsed"]["emergency_surcharge_pct"] == 8
    assert "Lucía Fernández" in result["summary"]
    assert "COP" in result["summary"]
    assert "brasaland-supplier-ordering.en.md" in _documents(result)
    assert "brasaland-menu-allergens.en.md" in _documents(result)
    assert any(item["id"] == "emergency_surcharge" and item["status"] == "pass" for item in result["compliance"]["checks"])
    assert any(item["id"] == "health_authority" and item["status"] == "pass" for item in result["compliance"]["checks"])


def test_florida_packaging_uses_usd() -> None:
    result = review_supplier_application({"raw_text": FLORIDA_PACKAGING})
    assert result["decision"] == "approve"
    assert result["market"] == "Florida"
    assert result["currency"] == "USD"
    assert result["parsed"]["categories"] == ["packaging"]
    assert "USD" in result["summary"]
    assert not any(item["id"] == "health_authority" for item in result["compliance"]["checks"])


def test_zero_cross_contamination_promise_is_rejected() -> None:
    result = review_supplier_application({"raw_text": ZERO_RISK_SAUCE})
    assert result["decision"] == "reject"
    assert result["currency"] == "USD"
    failed = [item for item in result["compliance"]["checks"] if item["id"] == "cross_contamination"]
    assert failed and failed[0]["status"] == "fail"
    assert "brasaland-menu-allergens.en.md" in _documents(result)
    assert "Do not approve" in result["summary"]


def test_surcharge_mismatch_is_a_condition() -> None:
    result = review_supplier_application({"raw_text": HIGH_SURCHARGE})
    assert result["decision"] == "approve_with_conditions"
    assert result["currency"] == "COP"
    assert any("8%" in item for item in result["conditions"])


def test_incomplete_application_is_rejected() -> None:
    result = review_supplier_application(
        {"raw_text": "Country: Colombia\nCategories: proteins\nEmergency surcharge: 8%\nINVIMA registered."}
    )
    assert result["decision"] == "reject"
    assert result["parsed"]["complete"] is False
    assert any("name" in gap.lower() for gap in result["parsed"]["gaps"])


def test_empty_knowledge_base_does_not_invent_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    def _empty(question: str, k: int = 3) -> dict:
        return {"answer": "There is not enough information available to answer this question.", "sources": []}

    monkeypatch.setattr("agents.supplier_approval.compliance_agent.query_standards", _empty)
    result = review_supplier_application({"raw_text": COLOMBIA_PROTEIN})
    assert result["decision"] == "approve_with_conditions"
    knowledge = [item for item in result["compliance"]["checks"] if item["id"] == "knowledge_base"]
    assert knowledge and knowledge[0]["status"] == "condition"
    assert not any(item["id"] == "emergency_surcharge" for item in result["compliance"]["checks"])
    assert not any(item["id"] == "health_authority" for item in result["compliance"]["checks"])


def test_groq_rewrite_uses_the_existing_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _Message:
        content = "Decision: approve\nCarnes Andinas may supply proteins in Colombia. Currency stays COP."

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = _Chat()

    monkeypatch.setenv("BRASALAND_SUPPLIER_AGENTS", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("openai.OpenAI", _Client)
    result = review_supplier_application({"raw_text": COLOMBIA_PROTEIN})
    assert result["llm"] == "used"
    assert result["decision"] == "approve"
    assert captured["client"]["base_url"] == "https://api.groq.com/openai/v1"
    assert result["summary"].startswith("Decision: approve")


def test_review_route_requires_a_staff_token(client: TestClient) -> None:
    missing = client.post("/suppliers/applications/review", json={"raw_text": COLOMBIA_PROTEIN})
    assert missing.status_code == 401
    response = client.post(
        "/suppliers/applications/review",
        headers=_headers(client),
        json={"raw_text": COLOMBIA_PROTEIN},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "approve"
    assert body["currency"] == "COP"
    assert body["roles"] == ["supplier", "compliance", "operations"]
    paths = client.get("/openapi.json").json()["paths"]
    assert "/suppliers/applications/review" in paths


def test_review_route_rejects_an_empty_body(client: TestClient) -> None:
    response = client.post(
        "/suppliers/applications/review",
        headers=_headers(client),
        json={"raw_text": "   "},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"


def test_agent_entry_point_prints_the_summary() -> None:
    completed = subprocess.run(
        [sys.executable, "agent.py", "review-supplier", FLORIDA_PACKAGING],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    body = json.loads(completed.stdout)
    assert body["decision"] == "approve"
    assert body["currency"] == "USD"
    assert body["roles"] == ["supplier", "compliance", "operations"]
