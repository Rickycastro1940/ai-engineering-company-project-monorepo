import os
import sys
from pathlib import Path
import pandas as pd
from datetime import timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
from prefect import flow, task
from prefect.tasks import task_input_hash

# 1. Explicitly find the .env file at the root of the project
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# 2. Safely grab the variables
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# 3. Add a safeguard to catch missing keys immediately
if not url or not key:
    print(f"❌ ERROR: Could not find Supabase credentials. Looking for .env at: {env_path}")
    sys.exit(1)

# Initialize the Supabase client
supabase: Client = create_client(url, key)

# ... (rest of your tasks and flow below)
import os
import pandas as pd
from datetime import timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
from prefect import flow, task
from prefect.tasks import task_input_hash

# Load environment variables from the .env file
load_dotenv()

# Initialize the Supabase client
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# ------------------------------------------------------------------
# PHASE 1: EXTRACTION TASKS
# Retries added (retries=3) to handle transient database timeouts
# ------------------------------------------------------------------

@task(retries=3, retry_delay_seconds=5)
def extract_telemetry_events(start_date: str, end_date: str) -> pd.DataFrame:
    print(f"Extracting telemetry events from {start_date} to {end_date}...")
    
    # Query Supabase for Brasaland's business events
    response = supabase.table("telemetry_events").select("*").in_("event_type", [
        "inbound_order_created", 
        "stock_waste_registered", 
        "stock_threshold_triggered", 
        "ingredient_price_variance_detected"
    ]).gte("created_at", start_date).lt("created_at", end_date).execute()
    
    return pd.DataFrame(response.data)

@task(retries=3, retry_delay_seconds=5)
def extract_domain_data() -> pd.DataFrame:
    print("Extracting Brasaland locations domain data...")
    # Pull locations to map IDs to countries/currencies
    response = supabase.table("locations").select("id, country, currency").execute()
    return pd.DataFrame(response.data)

# ------------------------------------------------------------------
# PHASE 2: TRANSFORMATION TASK
# Caching added: Cache key is based on the task's inputs. 
# Cache expires in 1 day so we don't recalculate the exact same week twice.
# ------------------------------------------------------------------

@task(cache_key_fn=task_input_hash, cache_expiration=timedelta(days=1))
def aggregate_location_kpis(telemetry_df: pd.DataFrame, locations_df: pd.DataFrame, week_start: str) -> pd.DataFrame:
    print("Aggregating KPIs: Purchase Cost, Waste Cost, Waste Ratio, Stockouts, Price Alerts...")
    
    if telemetry_df.empty:
        print("No telemetry events found for this timeframe.")
        return pd.DataFrame()
        
    # Extract nested JSON properties into standard pandas columns
    telemetry_df['location_id'] = telemetry_df['event_payload'].apply(lambda x: x.get('location_id'))
    telemetry_df['cost'] = telemetry_df['event_payload'].apply(lambda x: float(x.get('cost', 0)))
    
    kpis = []
    
    # Group events by each physical Brasaland restaurant location
    grouped = telemetry_df.groupby('location_id')
    
    for location_id, group in grouped:
        purchases = group[group['event_type'] == 'inbound_order_created']
        wastes = group[group['event_type'] == 'stock_waste_registered']
        stockouts = group[group['event_type'] == 'stock_threshold_triggered']
        price_alerts = group[group['event_type'] == 'ingredient_price_variance_detected']
        
        purchase_cost = purchases['cost'].sum()
        waste_cost = wastes['cost'].sum()
        waste_ratio = (waste_cost / purchase_cost) if purchase_cost > 0 else 0
        
        kpis.append({
            "location_id": location_id,
            "week_start": week_start,
            "total_purchase_cost": purchase_cost,
            "total_waste_cost": waste_cost,
            "waste_ratio": round(waste_ratio, 4),
            "stockout_events_count": len(stockouts),
            "price_alert_events_count": len(price_alerts)
        })
        
    kpis_df = pd.DataFrame(kpis)
    
    # Map country and currency from domain data
    if not locations_df.empty and not kpis_df.empty:
        kpis_df = kpis_df.merge(locations_df, left_on='location_id', right_on='id', how='left')
        kpis_df['country'] = kpis_df['country'].fillna('Unknown')
        kpis_df['currency'] = kpis_df['currency'].fillna('USD')
        if 'id' in kpis_df.columns:
            kpis_df = kpis_df.drop(columns=['id'])
            
    return kpis_df

# ------------------------------------------------------------------
# PHASE 3: LOAD TASK
# Idempotent load using upsert to avoid duplicate records
# ------------------------------------------------------------------

@task(retries=3, retry_delay_seconds=5)
def upsert_to_reporting_table(kpis_df: pd.DataFrame):
    if kpis_df.empty:
        print("No KPI data to upsert.")
        return
        
    print("Upserting aggregated KPIs to reporting.weekly_location_performance...")
    records = kpis_df.to_dict(orient="records")
    
    # Upsert relies on the unique constraint (location_id, week_start)
    # If the pipeline runs twice, it overwrites the existing record instead of duplicating.
    response = supabase.table("weekly_location_performance").upsert(
        records, 
        on_conflict="location_id,week_start"
    ).execute()
    
    print(f"Successfully upserted {len(records)} records.")

# ------------------------------------------------------------------
# OPTIONAL EXPORT TASK (Partial Failure Example)
# ------------------------------------------------------------------

@task(retries=1)
def optional_secondary_export(kpis_df: pd.DataFrame):
    # This intentionally mimics a flaky external storage system like S3
    print("Attempting to export a CSV backup...")
    raise Exception("Simulated connection timeout to CSV Backup Storage")

# ------------------------------------------------------------------
# MAIN FLOW
# ------------------------------------------------------------------

@flow(name="brasaland_weekly_cost_waste_flow", log_prints=True)
def run_pipeline(start_date: str, end_date: str):
    print(f"--- Starting pipeline run for {start_date} to {end_date} ---")
    
    # 1. Extract
    telemetry_data = extract_telemetry_events(start_date, end_date)
    records_processed = len(telemetry_data)
    domain_data = extract_domain_data()
    
    # 2. Transform
    kpis = aggregate_location_kpis(telemetry_data, domain_data, start_date)
    
    # 3. Load
    upsert_to_reporting_table(kpis)

    # 4. Partial Failure Example (return_state=True)
    # If this task fails, it does NOT crash the pipeline. It just returns a failed state.
    export_state = optional_secondary_export(kpis, return_state=True)
    if export_state.is_failed():
        print(f"⚠️ Non-critical task failed: {export_state.message}. Flow will continue.")

    # 5. Execution Logging
    print(f"--- Pipeline Execution Complete ---")
    print(f"Metadata Log: Start={start_date}, End={end_date}, Records Processed={records_processed}, Status=Success")

# Phase 4 Requirement: Allow execution as a CLI script
if __name__ == "__main__":
    import sys
    # Test run for a sample week
    run_pipeline("2026-07-08", "2026-07-15")
    
    # Force a clean exit to prevent background threads from crashing during shutdown
    os._exit(0)
    # Test run for a sample week
    run_pipeline("2026-07-08", "2026-07-15")
    if __name__ == "__main__":
    import os
    # Test run for a sample week
    run_pipeline("2026-07-08", "2026-07-15")
    
    # Hard exit to bypass Prefect's buggy SQLite teardown in Python 3.12
    os._exit(0)