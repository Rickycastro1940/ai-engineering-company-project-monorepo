from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from analyzer import IncidentAnalyzer
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from inventory import router as inventory_csv_router
from locations import router as locations_router
from errors import register_error_handlers
from pydantic import BaseModel, Field
from sqlmodel import Session
from users import ensure_seed_supervisor, router as users_router

from services.database import get_engine
from services.models import Ingredient, IngredientEntry, IngredientExit  # noqa: F401
from services.routers import inventory_router
from services.seed_inventory import seed_inventory

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_ROOT = REPO_ROOT / "uis" / "web"
UPLOAD_DIR = REPO_ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
Engine = Literal["native", "pandas"]

class AnalyzeRequest(BaseModel):
    input_file: str = Field(default="scripts/incidents-COMPANY.csv")
    output_file: str = Field(default="results.csv")
    engine: Engine = "native"

def _resolve_repo_path(path_value: str) -> Path:
    candidate = Path(path_value)
    resolved = candidate.resolve() if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()
    if not str(resolved).startswith(str(REPO_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="Path must stay inside the repository")
    return resolved

def _run_analysis(input_path: Path, output_path: Path, engine: Engine) -> dict:
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Input CSV was not found.")
    try:
        analyzer = IncidentAnalyzer.from_file(input_path, engine=engine)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Input CSV was not found.") from error
    except (OSError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail="The input CSV could not be read.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail="The input CSV is not valid incident data.") from error

    try:
        analyzer.export_summary_to_csv(output_path)
    except OSError as error:
        raise HTTPException(status_code=500, detail="Could not write the analysis results file.") from error

    summary = analyzer.build_summary()
    try:
        summary["output_file"] = str(output_path.relative_to(REPO_ROOT))
    except ValueError:
        summary["output_file"] = output_path.name
    return summary

def _register_analyze_routes(app: FastAPI, route_prefix: str) -> None:
    @app.post(f"/api/incidents/{route_prefix}")
    def analyze(request: AnalyzeRequest):
        out = _resolve_repo_path(request.output_file)
        _run_analysis(_resolve_repo_path(request.input_file), out, request.engine)
        return FileResponse(path=out, filename=out.name, media_type="text/csv")

    @app.post(f"/api/incidents/{route_prefix}/summary")
    def analyze_summary(request: AnalyzeRequest):
        return _run_analysis(_resolve_repo_path(request.input_file), _resolve_repo_path(request.output_file), request.engine)

    @app.post(f"/api/incidents/{route_prefix}/upload")
    async def analyze_upload(file: UploadFile = File(...), output_file: str = Form(default="results.csv"), engine: Engine = Form(default="native")):
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only CSV uploads are supported")
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="incident-upload-", dir=UPLOAD_DIR))
        except OSError as error:
            raise HTTPException(status_code=500, detail="Could not store the upload.") from error
        input_path = temp_dir / file.filename
        output_path = _resolve_repo_path(output_file)
        try:
            with input_path.open("wb") as handle:
                shutil.copyfileobj(file.file, handle)
        except OSError as error:
            raise HTTPException(status_code=400, detail="The uploaded file could not be saved.") from error
        finally:
            await file.close()
        _run_analysis(input_path, output_path, engine)
        return FileResponse(path=output_path, filename=output_path.name, media_type="text/csv")

    @app.post(f"/api/incidents/{route_prefix}/upload/summary")
    async def analyze_upload_summary(file: UploadFile = File(...), output_file: str = Form(default="results.csv"), engine: Engine = Form(default="native")):
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only CSV uploads are supported")
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="incident-upload-", dir=UPLOAD_DIR))
        except OSError as error:
            raise HTTPException(status_code=500, detail="Could not store the upload.") from error
        input_path = temp_dir / file.filename
        output_path = _resolve_repo_path(output_file)
        try:
            with input_path.open("wb") as handle:
                shutil.copyfileobj(file.file, handle)
        except OSError as error:
            raise HTTPException(status_code=400, detail="The uploaded file could not be saved.") from error
        finally:
            await file.close()
        return _run_analysis(input_path, output_path, engine)

def _bootstrap_inventory() -> None:
    user_uuid = "1"
    if os.getenv("PYTEST_CURRENT_TEST") is None:
        user_uuid = str(ensure_seed_supervisor()["id"])
    with Session(get_engine()) as session:
        seed_inventory(session, user_uuid)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from sqlmodel import SQLModel

    from services.database import engine

    SQLModel.metadata.create_all(engine)
    _bootstrap_inventory()
    yield


app = FastAPI(title="Brasaland Central API", version="1.0.0", debug=False, lifespan=lifespan)
register_error_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(locations_router)
app.include_router(inventory_router)  # dedicated ORM inventory router, prefix=/inventory
app.include_router(inventory_csv_router)
app.include_router(users_router)
_register_analyze_routes(app, "anylayze")
_register_analyze_routes(app, "analyze")

@app.get("/api/incidents/results/export")
def export_results(output_file: str = "results.csv"):
    output_path = _resolve_repo_path(output_file)
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Results file not found.")
    return FileResponse(path=output_path, filename=output_path.name, media_type="text/csv")

if UI_ROOT.exists():
    app.mount("/", StaticFiles(directory=UI_ROOT, html=True), name="web-ui")
