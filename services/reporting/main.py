import os
import json
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

from services.tasks import run_weekly_pipeline
from services.task_status import get_task_payload

load_dotenv()

app = FastAPI(title="Brasaland Reporting API")

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

class PipelineTriggerRequest(BaseModel):
    start_date: str
    end_date: str

@app.get("/reporting/weekly-location-performance")
def get_weekly_performance(week_start: str = None):
    query = supabase.table("weekly_location_performance").select("*")
    if week_start:
        query = query.eq("week_start", week_start)
    
    response = query.order("week_start", desc=True).execute()
    
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
    async_result = run_weekly_pipeline.delay(payload.start_date, payload.end_date)
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
        with open("data/pipelines/last_run.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"message": "No pipeline runs recorded yet."}

# Mount the frontend UI (must be at the bottom)
app.mount("/", StaticFiles(directory="uis/backoffice", html=True), name="ui")
