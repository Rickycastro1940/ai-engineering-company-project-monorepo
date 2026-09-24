"""Assert Prefect / table / KPI names match PIPELINE_DESIGN.md + CONTEXT-company.md.

A generic retail model (business_metrics, miami-downtown, sku, etc.) must not appear.
"""
from __future__ import annotations

from data.process.location_kpis import KPI_EVENT_TYPES, REPORTING_COLUMNS
from data.pipelines import pipeline as mod
from services.reporting import schemas as reporting_schemas


# CONTEXT-company.md / PIPELINE_DESIGN.md — destination + run log
EXPECTED_PERFORMANCE_TABLE = "weekly_location_performance"
EXPECTED_RUNS_TABLE = "pipeline_runs"
EXPECTED_SCHEMA = "reporting"
EXPECTED_UPSERT_CONFLICT = "location_id,week_start"

EXPECTED_KPI_EVENT_TYPES = (
    "inbound_order_created",
    "stock_waste_registered",
    "stock_threshold_triggered",
    "ingredient_price_variance_detected",
)

EXPECTED_REPORTING_COLUMNS = [
    "location_id",
    "week_start",
    "total_purchase_cost",
    "total_waste_cost",
    "waste_ratio",
    "stockout_events_count",
    "price_alert_events_count",
    "country",
    "currency",
]

# PIPELINE_DESIGN.md Phase 4 — Prefect name= contract (Part 3 subflows + tasks)
EXPECTED_MAIN_FLOW = "brasaland_weekly_performance_pipeline"
EXPECTED_SUBFLOWS = {
    "extract_brasaland_data_flow",
    "transform_brasaland_kpis_flow",
    "load_brasaland_reporting_flow",
}
EXPECTED_TASKS = {
    "extract_telemetry_events",
    "extract_domain_data",
    "land_raw_extracts",
    "aggregate_location_kpis",
    "land_kpi_intermediate",
    "upsert_to_reporting_table",
    "write_eval_snapshot",
}

# CONTEXT.md roster samples (not fixture labels)
EXPECTED_ROSTER_SAMPLES = {"co-med-centro", "us-mia-downtown", "co-bog-norte", "us-orlando"}
FORBIDDEN_FIXTURE_LABELS = {"miami-downtown", "medellin-centro", "miami_downtown"}
FORBIDDEN_TABLES = {"business_metrics", "weekly_location_metrics", "metrics"}


def test_kpi_event_types_match_context_company():
    assert KPI_EVENT_TYPES == EXPECTED_KPI_EVENT_TYPES


def test_reporting_columns_match_context_destination_table():
    assert REPORTING_COLUMNS == EXPECTED_REPORTING_COLUMNS
    assert list(mod._KPI_LOAD_COLUMNS) == EXPECTED_REPORTING_COLUMNS


def test_table_and_schema_names_match_context_company():
    assert mod._REPORTING_SCHEMA == EXPECTED_SCHEMA
    assert mod._PERFORMANCE_TABLE == EXPECTED_PERFORMANCE_TABLE
    assert mod._RUNS_TABLE == EXPECTED_RUNS_TABLE
    assert mod._UPSERT_CONFLICT == EXPECTED_UPSERT_CONFLICT
    assert "business_metrics" not in mod._PERFORMANCE_TABLE
    assert "weekly_location_metrics" not in mod._PERFORMANCE_TABLE


def test_prefect_flow_and_task_names_match_pipeline_design():
    assert mod.run_pipeline.name == EXPECTED_MAIN_FLOW
    assert mod.extract_brasaland_data_flow.name in EXPECTED_SUBFLOWS
    assert mod.transform_brasaland_kpis_flow.name in EXPECTED_SUBFLOWS
    assert mod.load_brasaland_reporting_flow.name in EXPECTED_SUBFLOWS

    task_names = {
        mod.extract_telemetry_events.name,
        mod.extract_domain_data.name,
        mod.land_raw_extracts.name,
        mod.aggregate_location_kpis.name,
        mod.land_kpi_intermediate.name,
        mod.upsert_to_reporting_table.name,
        mod.write_eval_snapshot.name,
    }
    assert task_names == EXPECTED_TASKS


def test_kpi_response_schema_fields_match_context_example():
    fields = set(reporting_schemas.WeeklyLocationPerformanceRow.model_fields)
    assert fields == {
        "location_id",
        "country",
        "currency",
        "total_purchase_cost",
        "total_waste_cost",
        "waste_ratio",
        "stockout_events_count",
        "price_alert_events_count",
    }
    # week_start belongs on the envelope, not each location object (CONTEXT example)
    assert "week_start" not in fields
    envelope = set(reporting_schemas.WeeklyLocationPerformanceResponse.model_fields)
    assert envelope == {"week_start", "locations"}


def test_pipeline_run_schema_fields_match_context_company():
    fields = set(reporting_schemas.PipelineRunLatestResponse.model_fields)
    required = {
        "run_id",
        "started_at",
        "finished_at",
        "window_start",
        "window_end",
        "records_processed",
        "status",
        "error_message",
    }
    assert required.issubset(fields)


def test_eval_fixtures_use_brasaland_roster_ids_not_generic_labels():
    import json
    from pathlib import Path

    fixtures = json.loads(
        (Path(__file__).resolve().parents[2] / "data/eval/weekly_location_performance_fixtures.json").read_text(
            encoding="utf-8"
        )
    )
    location_ids = {loc["location_id"] for loc in fixtures["locations"]}
    assert location_ids & EXPECTED_ROSTER_SAMPLES
    assert location_ids.isdisjoint(FORBIDDEN_FIXTURE_LABELS)
    for loc in fixtures["locations"]:
        assert loc["country"] in {"Colombia", "United States"}
        assert loc["currency"] in {"COP", "USD"}
        for event in loc["events"]:
            assert event["event_type"] in EXPECTED_KPI_EVENT_TYPES
            assert "location_id" in event["event_payload"]
            assert event["event_payload"]["location_id"] == loc["location_id"]


def test_no_forbidden_generic_table_aliases_in_pipeline_module():
    from pathlib import Path

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "business_metrics" not in source
    assert "weekly_location_metrics" not in source
    assert 'miami-downtown' not in source
    assert "medellin-centro" not in source
