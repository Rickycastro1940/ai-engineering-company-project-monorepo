"""Evaluate: same backend API-only pipeline under data/pipelines/ — no second HTTP service.

CONTEXT §2.4:
- HTTP: extend existing backend under services/ — no new API process
- Pipeline / graph: data/pipelines/rfp_intake/ (routers import and trigger; they do not own agent logic)
- Standalone CLIs: scripts/ if needed
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake import run_intake_from_bytes, run_intake_pipeline
from data.pipelines.rfp_intake.constants import STATUS_DISCARDED, STATUS_INTAKE_COMPLETE
from data.pipelines.rfp_intake.context_rules import CONTEXT_SEED_EXPECTATIONS
from services.rfp import router as rfp_router
from services.rfp.store import init_db, reset_engine

REPO = Path(__file__).resolve().parents[2]
PIPELINE = REPO / "data" / "pipelines" / "rfp_intake"
SERVICES_RFP = REPO / "services" / "rfp"
SEEDS = REPO / "rfp-requests" / "brasaland"

# Forbidden second-service layouts for RFP intake
FORBIDDEN_RFP_SERVICE_DIRS = (
    "services/rfp_api",
    "services/rfp_service",
    "services/rfp_intake_api",
    "services/rfp_http",
    "services/rfp_server",
)


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_pipeline_package_has_no_http_framework() -> None:
    """data/pipelines/rfp_intake must be API-agnostic pipeline code only."""
    assert PIPELINE.is_dir()
    forbidden = ("fastapi", "uvicorn", "starlette", "APIRouter", "Flask", "aiohttp")
    for path in _py_files(PIPELINE):
        src = path.read_text(encoding="utf-8")
        lower = src.casefold()
        for token in forbidden:
            assert token.casefold() not in lower, (
                f"{path.relative_to(REPO)} must not reference HTTP framework {token!r}"
            )


def test_no_second_rfp_http_service_package() -> None:
    for rel in FORBIDDEN_RFP_SERVICE_DIRS:
        assert not (REPO / rel).exists(), f"Forbidden second API package: {rel}"
    # Thin router package is OK; a dedicated app.py entrypoint under services/rfp is not.
    assert not (SERVICES_RFP / "app.py").exists()
    assert not (SERVICES_RFP / "main.py").exists()


def test_canonical_host_is_existing_agent_app_not_new_process() -> None:
    agent_app = (REPO / "services" / "agent" / "app.py").read_text(encoding="utf-8")
    assert "from services.rfp import router" in agent_app
    assert "include_router(rfp_router)" in agent_app
    # Same router module — not a copy — if reporting also mounts it.
    reporting = REPO / "services" / "reporting" / "main.py"
    if reporting.is_file():
        src = reporting.read_text(encoding="utf-8")
        if "rfp_router" in src:
            assert "from services.rfp import router" in src


def test_http_router_is_thin_and_delegates_to_pipeline() -> None:
    routes = (SERVICES_RFP / "routes.py").read_text(encoding="utf-8")
    assert "from data.pipelines.rfp_intake import" in routes
    assert "run_intake_from_bytes" in routes
    # Router must not own classifier / orchestrator / worker logic.
    for banned in (
        "def classifier_agent",
        "def classify_document",
        "def orchestrator",
        "def department_worker",
        "def synthesizer",
        "def run_intake_pipeline",
    ):
        assert banned not in routes, f"routes.py must not define {banned}"


def test_agent_logic_lives_only_under_data_pipelines() -> None:
    expected = {
        "classifier_agent": PIPELINE / "classifier.py",
        "orchestrator": PIPELINE / "orchestration.py",
        "department_worker": PIPELINE / "orchestration.py",
        "synthesizer": PIPELINE / "orchestration.py",
        "run_intake_pipeline": PIPELINE / "__init__.py",
        "route_intake_to_part2": PIPELINE / "routing.py",
    }
    for name, path in expected.items():
        src = path.read_text(encoding="utf-8")
        assert f"def {name}" in src, f"missing {name} in {path.name}"

    # services/rfp must not redefine those pipeline callables
    for path in _py_files(SERVICES_RFP):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        for name in expected:
            assert name not in defs, f"{path.name} must not define pipeline function {name}"


def test_cli_and_http_share_same_pipeline_entrypoints() -> None:
    cli = (REPO / "scripts" / "rfp_intake_smoke.py").read_text(encoding="utf-8")
    assert "from data.pipelines.rfp_intake import" in cli
    assert "run_intake_pipeline" in cli
    assert "FastAPI" not in cli
    assert "uvicorn" not in cli

    routes = (SERVICES_RFP / "routes.py").read_text(encoding="utf-8")
    assert "run_intake_from_bytes" in routes
    # run_intake_from_bytes is the byte/upload wrapper around run_intake_pipeline
    init_src = (PIPELINE / "__init__.py").read_text(encoding="utf-8")
    assert "def run_intake_from_bytes" in init_src
    assert "run_intake_pipeline(" in init_src


@pytest.mark.parametrize(
    "filename",
    [
        "CONTEXT-brasaland-request-1.pdf",
        "CONTEXT-brasaland-request-2.pdf",
        "CONTEXT-brasaland-request-3.pdf",
    ],
)
def test_api_and_direct_pipeline_same_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str
) -> None:
    """HTTP upload and direct pipeline call must use the same code and agree."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'same-pipe.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()

    pdf = SEEDS / filename
    expected = CONTEXT_SEED_EXPECTATIONS[filename]

    direct = run_intake_pipeline(pdf_path=pdf)
    raw = pdf.read_bytes()
    via_bytes, _ = run_intake_from_bytes(
        raw=raw, filename=filename, store_dir=tmp_path / "raw" / filename
    )

    app = FastAPI()
    app.include_router(rfp_router)
    client = TestClient(app)
    with pdf.open("rb") as fh:
        http = client.post(
            "/rfp/tickets",
            files={"file": (filename, fh, "application/pdf")},
        )
    assert http.status_code == 200, http.text
    body = http.json()

    # Same pipeline outcomes across direct / bytes / HTTP
    assert direct.status == via_bytes.status == body["status"]
    if expected.get("accept"):
        assert body["status"] == STATUS_INTAKE_COMPLETE
        assert set(direct.departments_needed) == set(body["departments_needed"])
        assert set(direct.departments_needed) == set(expected["departments"])
        assert direct.requires_ceo_approval == body["requires_ceo_approval"]
    else:
        assert body["status"] == STATUS_DISCARDED
        assert direct.discard_reason
        assert body.get("discard_reason")
        assert direct.departments_needed == body.get("departments_needed") == []
