import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

from services.tasks import run_weekly_pipeline
from services.task_status import get_task_payload

load_dotenv()

app = FastAPI(title="Brasaland Reporting API")


def _supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise HTTPException(
            status_code=503,
            detail="Reporting is unavailable: SUPABASE_URL and SUPABASE_KEY must be set.",
        )
    return create_client(url, key)

class PipelineTriggerRequest(BaseModel):
    start_date: str
    end_date: str

@app.get("/reporting/weekly-location-performance")
def get_weekly_performance(week_start: str = None):
    try:
        query = _supabase_client().table("weekly_location_performance").select("*")
        if week_start:
            query = query.eq("week_start", week_start)
        response = query.order("week_start", desc=True).execute()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to read weekly location performance from reporting storage.",
        )

    if not response.data:
        return {"week_start": week_start, "locations": []}
        
    actual_week_start = week_start or response.data[0].get("week_start")
    locations = [row for row in response.data if row["week_start"] == actual_week_start]
    
    formatted_locations = [{
        "location_id": loc["location_id"],
        "country": loc["country"],
        "total_purchase_cost": loc["total_purchase_cost"],
        "total_waste_cost": loc["total_waste_cost"],
        "waste_ratio": loc["waste_ratio"],
        "stockout_events_count": loc["stockout_events_count"],
        "price_alert_events_count": loc["price_alert_events_count"],
        "currency": loc["currency"]
    } for loc in locations]

    return {
        "week_start": actual_week_start,
        "locations": formatted_locations
    }

@app.post("/reporting/pipeline-runs")
def trigger_pipeline(payload: PipelineTriggerRequest):
    """Enqueue the weekly pipeline as a Celery task; return immediately."""
    try:
        async_result = run_weekly_pipeline.delay(payload.start_date, payload.end_date)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue the weekly pipeline. Confirm Redis is running.",
        )
    return JSONResponse(
        status_code=202,
        content={"task_id": async_result.id},
    )

@app.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    """Return Celery task status/result from the Redis result backend."""
    return get_task_payload(task_id)

@app.get("/reporting/pipeline-runs/latest")
def get_latest_run():
    try:
        with open("data/pipelines/last_run.json", "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {"message": "No pipeline runs recorded yet."}
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="last_run.json is not valid JSON.")

# Mount the frontend UI (must be at the bottom)
app.mount("/", StaticFiles(directory="uis/backoffice", html=True), name="ui")
