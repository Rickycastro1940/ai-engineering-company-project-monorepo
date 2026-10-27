"""RFP registration publishes analyzing tickets on the staff SSE stream."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
for path in (str(API_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("NO_SALES_MONITOR", "0")

from api.app import app  # noqa: E402
import rfp_notifications as rfp  # noqa: E402
from rfp_router import iter_rfp_notifications  # noqa: E402
import users  # noqa: E402

ANDES = {
    "client_name": "Andes Tech Solutions",
    "location": "Medellín",
    "locations": "co-med-centro,co-med-elpoblado",
    "service_type": "weekly catering",
    "scope": "220 employees, 12-month contract, standard menu",
    "deadline": "2026-11-30",
    "budget_range": "48000000 COP/year",
    "departments_needed": "marketing,operaciones,procurement",
    "title": "Andes weekly catering",
}

SUNSET = {
    "client_name": "Sunset Bay Resorts",
    "location": "Florida",
    "locations": "us-mia-brickell,us-mia-downtown",
    "service_type": "co-branded concession",
    "scope": "3 Florida resorts, exclusivity and a new signature menu",
    "deadline": "2026-12-01",
    "budget_range": "60000-75000 USD/year",
    "departments_needed": "marketing,operaciones,procurement,training",
}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(users, "DATABASE_PATH", tmp_path / "company_api.db")
    monkeypatch.setattr(rfp, "DATABASE_PATH", tmp_path / "rfp_tickets.sqlite3")
    monkeypatch.setattr(rfp, "UPLOAD_ROOT", tmp_path / "rfp")
    rfp.reset_rfp_state()
    yield
    rfp.reset_rfp_state()


def _auth_headers(client) -> dict[str, str]:
    token = client.post(
        "/auth/register",
        json={"email": "camila.rfp@brasaland.test", "password": "secret-password", "name": "Camila Ospina"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _post_rfp(client, headers: dict[str, str], fields: dict[str, str], *, extra: dict[str, str] | None = None):
    data = dict(fields)
    if extra:
        data.update(extra)
    return client.post(
        "/rfp/tickets",
        headers=headers,
        data=data,
        files={"file": ("andes-request.pdf", b"%PDF-1.4 Andes catering request", "application/pdf")},
    )


def test_stream_and_registration_require_jwt() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app)
    stream = client.get("/notifications/stream")
    assert stream.status_code == 401
    assert "text/event-stream" not in stream.headers.get("content-type", "")
    listed = client.get("/rfp/tickets")
    assert listed.status_code == 401
    created = client.post("/rfp/tickets")
    assert created.status_code == 401


def test_registration_starts_analyzing_with_brasaland_rfp_fields() -> None:
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = _post_rfp(client, headers, ANDES, extra={"status": "escalated"})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "analyzing"
        assert body["terminal"] is False
        assert body["company"] == "brasaland"
        assert body["owner"] == "Camila Ospina"
        assert body["client_name"] == "Andes Tech Solutions"
        assert body["location"] == "Medellín"
        assert body["country"] == "Colombia"
        assert body["currency"] == "COP"
        assert [site["id"] for site in body["locations"]] == [
            "co-med-centro",
            "co-med-elpoblado",
        ]
        assert {site["currency"] for site in body["locations"]} == {"COP"}
        assert body["service_type"] == "weekly catering"
        assert body["scope"].startswith("220 employees")
        assert body["deadline"] == "2026-11-30"
        assert body["budget_range"] == "48000000 COP/year"
        assert body["departments_needed"] == ["marketing", "operaciones", "procurement"]
        assert body["rfp_id"].startswith("rfp_")
        assert body["ticket_id"]
        assert isinstance(body["event_id"], int)
        assert body["raw_pdf_path"].endswith("andes-request.pdf")
        assert "emergency_order" not in created.text
        assert "waste_escalation" not in created.text

        listed = client.get("/rfp/tickets", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["tickets"][0]["ticket_id"] == body["ticket_id"]
        assert listed.json()["tickets"][0]["status"] == "analyzing"

        detail = client.get(f"/rfp/tickets/{body['ticket_id']}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["budget_range"] == "48000000 COP/year"


def test_budget_must_keep_cop_or_usd_and_departments_are_brasaland_ids() -> None:
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        headers = _auth_headers(client)
        missing_currency = _post_rfp(
            client,
            headers,
            {**ANDES, "budget_range": "75000"},
        )
        assert missing_currency.status_code == 400
        foreign = _post_rfp(client, headers, {**ANDES, "budget_range": "75000 EUR/year"})
        assert foreign.status_code == 400
        unknown = _post_rfp(
            client,
            headers,
            {**ANDES, "departments_needed": "marketing,sales"},
        )
        assert unknown.status_code == 400
        mixed = _post_rfp(
            client,
            headers,
            {**ANDES, "locations": "co-med-centro,us-mia-brickell"},
        )
        assert mixed.status_code == 400
        wrong_market = _post_rfp(
            client,
            headers,
            {**SUNSET, "budget_range": "48000000 COP/year"},
        )
        assert wrong_market.status_code == 400
        empty = client.post(
            "/rfp/tickets",
            headers=headers,
            data=ANDES,
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert empty.status_code == 400


def test_sunset_budget_stays_in_usd() -> None:
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = _post_rfp(client, headers, SUNSET)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "analyzing"
        assert body["budget_range"] == "60000-75000 USD/year"
        assert body["location"] == "Florida"
        assert body["country"] == "United States"
        assert body["currency"] == "USD"
        assert [site["id"] for site in body["locations"]] == [
            "us-mia-brickell",
            "us-mia-downtown",
        ]
        assert "training" in body["departments_needed"]


def test_openapi_lists_rfp_registration_and_the_stream() -> None:
    paths = app.openapi()["paths"]
    assert "/rfp/tickets" in paths
    assert "/notifications/stream" in paths
    assert "post" in paths["/rfp/tickets"]


async def _next_frame(generator) -> str:
    return await asyncio.wait_for(generator.__anext__(), timeout=2)


def test_sse_emits_named_analyzing_event_and_replays_after_cursor() -> None:
    asyncio.run(_sse_round_trip())


async def _sse_round_trip() -> None:
    frames = iter_rfp_notifications(None)
    try:
        assert (await _next_frame(frames)).startswith(": keep-alive")
        first = rfp.register_rfp(
            client_name=ANDES["client_name"],
            location=ANDES["location"],
            locations=["co-med-centro", "co-med-elpoblado"],
            service_type=ANDES["service_type"],
            scope=ANDES["scope"],
            deadline=ANDES["deadline"],
            budget_range=ANDES["budget_range"],
            departments_needed=["marketing", "operaciones", "procurement"],
            original_filename="andes-request.pdf",
            file_bytes=b"%PDF andes",
            title=ANDES["title"],
        )
        rfp.hub.publish(first)
        live = await _next_frame(frames)
        assert "event: rfp_ticket_created" in live
        assert live.startswith(f"id: {first['event_id']}\n")
        payload = json.loads(live.split("data: ", 1)[1].strip())
        assert payload["status"] == "analyzing"
        assert payload["ticket_id"] == first["ticket_id"]
        assert payload["client_name"] == "Andes Tech Solutions"
        assert payload["budget_range"] == "48000000 COP/year"
        assert payload["currency"] == "COP"
        assert payload["locations"][0]["id"] == "co-med-centro"
        assert "us-mia" not in live
        assert payload["company"] == "brasaland"
        assert "emergency_order" not in live
        assert "waste" not in live
    finally:
        await frames.aclose()

    replay = iter_rfp_notifications(str(first["event_id"]))
    try:
        assert (await _next_frame(replay)).startswith(": keep-alive")
        second = rfp.register_rfp(
            client_name=SUNSET["client_name"],
            location=SUNSET["location"],
            locations=["us-mia-brickell", "us-mia-downtown"],
            service_type=SUNSET["service_type"],
            scope=SUNSET["scope"],
            deadline=SUNSET["deadline"],
            budget_range=SUNSET["budget_range"],
            departments_needed=["marketing", "operaciones", "procurement", "training"],
            original_filename="sunset-request.pdf",
            file_bytes=b"%PDF sunset",
        )
        rfp.hub.publish(second)
        nxt = await _next_frame(replay)
        assert "event: rfp_ticket_created" in nxt
        assert second["ticket_id"] in nxt
        assert first["ticket_id"] not in nxt
        assert "60000-75000 USD/year" in nxt
    finally:
        await replay.aclose()


def _read_sse_until(response, needle: str, *, max_chunks: int = 40) -> str:
    """Read the live HTTP stream until one frame contains needle."""
    text = ""
    for chunk in response.iter_text():
        text += chunk
        if needle in text:
            return text
        max_chunks -= 1
        if max_chunks <= 0:
            break
    raise AssertionError(f"SSE stream did not include {needle!r}. Saw: {text!r}")


def _named_event_payloads(text: str) -> list[dict]:
    payloads: list[dict] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        if "event: rfp_ticket_created" not in block:
            continue
        data_lines = [
            line.split(":", 1)[1].lstrip()
            for line in block.split("\n")
            if line.startswith("data:")
        ]
        if data_lines:
            payloads.append(json.loads("\n".join(data_lines)))
    return payloads


def test_http_stream_frames_named_rfp_ticket_created_event() -> None:
    """The SSE route itself, not a detached dict: headers, event name, and JSON data."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = _post_rfp(client, headers, ANDES)
        assert created.status_code == 201, created.text
        ticket_id = created.json()["ticket_id"]
        with client.stream("GET", "/notifications/stream", headers=headers, timeout=5) as response:
            assert response.status_code == 200
            content_type = response.headers["content-type"]
            assert content_type.startswith("text/event-stream")
            assert response.headers["cache-control"] == "no-cache"
            assert response.headers["x-accel-buffering"] == "no"
            wire = _read_sse_until(response, ticket_id)

    assert wire.startswith(": keep-alive")
    assert "event: message" not in wire
    assert "event: rfp_ticket_created" in wire
    payloads = _named_event_payloads(wire)
    assert payloads
    payload = next(row for row in payloads if row["ticket_id"] == ticket_id)
    assert payload["status"] == "analyzing"
    assert payload["terminal"] is False
    assert payload["company"] == "brasaland"
    assert payload["owner"] == "Camila Ospina"
    assert payload["client_name"] == "Andes Tech Solutions"
    assert payload["location"] == "Medellín"
    assert payload["country"] == "Colombia"
    assert payload["currency"] == "COP"
    assert payload["service_type"] == "weekly catering"
    assert payload["scope"].startswith("220 employees")
    assert payload["deadline"] == "2026-11-30"
    assert payload["budget_range"] == "48000000 COP/year"
    assert payload["departments_needed"] == ["marketing", "operaciones", "procurement"]
    assert [site["id"] for site in payload["locations"]] == [
        "co-med-centro",
        "co-med-elpoblado",
    ]
    assert payload["rfp_id"].startswith("rfp_")
    assert "emergency_order" not in wire
    assert "waste_escalation" not in wire


def test_reconnect_recovers_ticket_registered_while_disconnected() -> None:
    """Drop the stream, register during the gap, reconnect with Last-Event-ID once."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        headers = _auth_headers(client)
        first = _post_rfp(client, headers, ANDES)
        assert first.status_code == 201, first.text
        first_body = first.json()
        with client.stream("GET", "/notifications/stream", headers=headers, timeout=5) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            seen = _read_sse_until(response, first_body["ticket_id"])
        assert _named_event_payloads(seen)[0]["ticket_id"] == first_body["ticket_id"]

        missed = _post_rfp(client, headers, SUNSET)
        assert missed.status_code == 201, missed.text
        missed_body = missed.json()
        resumed = {**headers, "Last-Event-ID": str(first_body["event_id"])}
        with client.stream(
            "GET",
            "/notifications/stream",
            headers=resumed,
            timeout=5,
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            recovered = _read_sse_until(response, missed_body["ticket_id"])

    payloads = _named_event_payloads(recovered)
    ids = [row["ticket_id"] for row in payloads]
    assert ids == [missed_body["ticket_id"]]
    assert first_body["ticket_id"] not in ids
    assert payloads[0]["status"] == "analyzing"
    assert payloads[0]["budget_range"] == "60000-75000 USD/year"
    assert payloads[0]["currency"] == "USD"


def test_last_event_id_skips_older_registrations() -> None:
    older = rfp.register_rfp(
        client_name="Andes Tech Solutions",
        location="Medellín",
        locations=["co-med-centro"],
        service_type="weekly catering",
        scope="220 employees",
        deadline="2026-11-30",
        budget_range="48000000 COP/year",
        departments_needed=["marketing"],
        original_filename="a.pdf",
        file_bytes=b"a",
    )
    newer = rfp.register_rfp(
        client_name="Sunset Bay Resorts",
        location="Florida",
        locations=["us-mia-brickell"],
        service_type="concession",
        scope="3 resorts",
        deadline="2026-12-01",
        budget_range="60000-75000 USD/year",
        departments_needed=["training"],
        original_filename="b.pdf",
        file_bytes=b"b",
    )
    after = rfp.tickets_after(str(older["event_id"]))
    assert [row["ticket_id"] for row in after] == [newer["ticket_id"]]
    assert rfp.tickets_after(str(newer["event_id"])) == []
    encoded = rfp.encode_ticket_event(newer)
    assert encoded.startswith(f"id: {newer['event_id']}\n")
    assert "event: rfp_ticket_created\n" in encoded
