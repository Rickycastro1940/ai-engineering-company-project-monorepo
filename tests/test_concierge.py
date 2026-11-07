"""Guest concierge: COP/USD menu, allergens, orders, WebSocket, SSE, and voice fallback."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
for path in (str(API_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.app import app  # noqa: E402
from menus import list_menu_items  # noqa: E402
from locations import location_roster  # noqa: E402
from services.concierge.answers import money_cop, money_usd, reply  # noqa: E402
from services.concierge.routes import router as concierge_router  # noqa: E402
from services.concierge.session import reset_concierge_state  # noqa: E402
from services.knowledge.routes import router as knowledge_router  # noqa: E402
from services.concierge.transcribe import transcribe_with_model  # noqa: E402
import sales  # noqa: E402
import users  # noqa: E402

ORDER = "Two grilled sirloin at Medellín Centro"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("NO_SALES_MONITOR", "0")
    monkeypatch.delenv("BRASALAND_AUDIO_API_KEY", raising=False)
    monkeypatch.setattr(users, "DATABASE_PATH", tmp_path / "company_api.db")
    reset_concierge_state()
    yield
    reset_concierge_state()


def _item(item_id: str):
    return next(item for item in list_menu_items() if item.id == item_id)


def _session(client: TestClient) -> str:
    created = client.post("/concierge/sessions")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["session_id"].startswith("BRS-GUEST-")
    assert body["thread_id"] == body["session_id"]
    assert body["company"] == "brasaland"
    assert body["agent_id"] == "guest_concierge"
    assert len(location_roster()) == 14
    return body["session_id"]


def _ask(client: TestClient, session_id: str, content: str) -> dict:
    response = client.post(
        f"/concierge/sessions/{session_id}/messages",
        json={"content": content},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_menu_answer_uses_catalogue_prices_in_cop_and_usd() -> None:
    sirloin = _item("grilled-sirloin")
    session: dict = {"order": None}
    answer = reply(session, "How much is the grilled sirloin in Florida?")
    assert money_cop(sirloin.price_cop) in answer
    assert money_usd(sirloin.price_usd) in answer
    assert "USD" in answer and "COP" in answer


def test_allergen_answer_comes_from_the_menu_item() -> None:
    sauce = _item("house-sauce")
    session: dict = {"order": None}
    answer = reply(session, "What allergens are in the House Sauce?")
    for allergen in sauce.allergens:
        assert allergen in answer
    assert "Zero cross-contamination risk is never guaranteed." in answer
    assert money_cop(sauce.price_cop) in answer
    assert money_usd(sauce.price_usd) in answer


def test_conversational_order_prices_the_location_currency_and_the_other() -> None:
    sirloin = _item("grilled-sirloin")
    client = TestClient(app)
    session_id = _session(client)
    before = len(sales._SALES)
    draft = _ask(client, session_id, ORDER)
    assert money_cop(sirloin.price_cop * 2) in draft["answer"]
    assert money_usd(sirloin.price_usd * 2) in draft["answer"]
    assert "Medellín Centro" in draft["answer"]
    assert draft["session"]["order"]["status"] == "draft"
    assert draft["session"]["order"]["currency"] == "COP"
    placed = _ask(client, session_id, "confirm")
    assert "Placed at Medellín Centro" in placed["answer"]
    assert placed["session"]["order"]["status"] == "placed"
    assert len(sales._SALES) == before

    anonymous = client.get("/concierge/orders")
    assert anonymous.status_code == 401
    token = client.post(
        "/auth/register",
        json={"email": "felipe.concierge@brasaland.test", "password": "secret-password"},
    ).json()["access_token"]
    listed = client.get("/concierge/orders", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200, listed.text
    orders = listed.json()["orders"]
    assert orders[-1]["location_id"] == "co-med-centro"
    assert orders[-1]["lines"][0]["item_id"] == "grilled-sirloin"
    assert orders[-1]["lines"][0]["quantity"] == 2
    assert orders[-1]["total_cop"] == sirloin.price_cop * 2


def test_ambiguous_location_and_unknown_dish_do_not_invent_a_kitchen_or_plate() -> None:
    session: dict = {"order": None}
    miami = reply(session, "Order a grilled sirloin in Miami")
    assert "Miami Brickell" in miami
    assert "Miami Downtown" in miami
    assert session["order"] is None or not (session.get("order") or {}).get("lines")
    unknown = reply({"order": None}, "Order the lobster roll at Medellín Centro")
    assert "lobster" not in unknown.lower() or "which dish" in unknown.lower()
    assert "Grilled Sirloin" in unknown


def test_websocket_streams_token_chunks() -> None:
    client = TestClient(app)
    session_id = _session(client)
    with client.websocket_connect(f"/concierge/ws?session_id={session_id}") as socket:
        hello = socket.receive_json()
        assert hello["event"] == "concierge_session"
        assert hello["agent_id"] == "guest_concierge"
        socket.send_json({"event": "concierge_user_message", "content": "How much is the corn arepa?"})
        frames = []
        while True:
            frame = socket.receive_json()
            frames.append(frame)
            if frame["event"] == "generation_completed":
                break
    deltas = "".join(frame["delta"] for frame in frames if frame["event"] == "token_chunk")
    done = frames[-1]
    assert deltas == done["content"]
    arepa = _item("corn-arepa")
    assert money_cop(arepa.price_cop) in done["content"]
    assert money_usd(arepa.price_usd) in done["content"]
    assert done["thread_id"] == session_id


def test_unknown_session_closes_the_socket() -> None:
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect("/concierge/ws?session_id=BRS-GUEST-missing") as socket:
            socket.receive_json()
    assert caught.value.code == 4404


def test_interrupt_stops_further_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRASALAND_CONCIERGE_TOKEN_DELAY", "0.05")
    client = TestClient(app)
    session_id = _session(client)
    with client.websocket_connect(f"/concierge/ws?session_id={session_id}") as socket:
        assert socket.receive_json()["event"] == "concierge_session"
        socket.send_json({"event": "concierge_user_message", "content": "Show me the full menu and prices"})
        saw_token = False
        final = None
        while final is None:
            frame = socket.receive_json()
            if frame["event"] == "token_chunk" and not saw_token:
                saw_token = True
                socket.send_json({"event": "interrupt"})
            if frame["event"] == "generation_interrupted":
                final = frame
    assert saw_token
    assert final is not None
    assert final["status"] == "interrupted"
    full = reply({"order": None}, "Show me the full menu and prices")
    assert len(final["content"]) < len(full)


def test_sse_replays_token_chunks_with_last_event_id() -> None:
    client = TestClient(app)
    session_id = _session(client)
    sirloin = _item("grilled-sirloin")
    _ask(client, session_id, "How much is the grilled sirloin?")
    with client.stream(
        "GET",
        f"/realtime/concierge/stream?session_id={session_id}",
        headers={"Last-Event-ID": "0"},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = ""
        for chunk in response.iter_text():
            body += chunk
            if "generation_completed" in body and "token_chunk" in body:
                break
    assert "event: token_chunk" in body
    assert "event: generation_completed" in body
    assert money_cop(sirloin.price_cop) in body
    assert money_usd(sirloin.price_usd) in body
    missing = client.get("/realtime/concierge/stream?session_id=BRS-GUEST-missing")
    assert missing.status_code == 404


def test_text_fallback_when_no_audio_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args, **_kwargs):
        raise AssertionError("audio model must not be called without a key")

    monkeypatch.setattr("services.concierge.transcribe.transcribe_with_model", _boom)
    client = TestClient(app)
    typed = client.post("/concierge/transcribe", json={"text": ORDER})
    assert typed.status_code == 200, typed.text
    assert typed.json()["mode"] == "text_fallback"
    assert typed.json()["transcript"] == ORDER
    assert typed.json()["audio_configured"] is False

    audio = client.post(
        "/concierge/transcribe",
        files={"audio": ("order.webm", b"not-really-audio", "audio/webm")},
    )
    assert audio.status_code == 200, audio.text
    body = audio.json()
    assert body["mode"] == "text_fallback"
    assert body["transcript"] == ""
    assert "No audio key" in body["detail"]

    session_id = _session(client)
    placed = _ask(client, session_id, typed.json()["transcript"])
    assert "Medellín Centro" in placed["answer"]
    assert "96,000 COP" in placed["answer"] or money_cop(_item("grilled-sirloin").price_cop * 2) in placed["answer"]


def test_configured_audio_model_transcribes_a_voice_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRASALAND_AUDIO_API_KEY", "test-audio-key")
    monkeypatch.setenv("BRASALAND_AUDIO_MODEL", "brasaland-whisper-test")

    def _fake(audio: bytes, filename: str, content_type: str) -> str:
        assert audio == b"voice-bytes"
        assert filename == "order.webm"
        assert content_type == "audio/webm"
        return "Two grilled sirloin at Medellín Centro"

    monkeypatch.setattr("services.concierge.transcribe.transcribe_with_model", _fake)
    client = TestClient(app)
    response = client.post(
        "/concierge/transcribe",
        files={"audio": ("order.webm", b"voice-bytes", "audio/webm")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "model"
    assert body["model"] == "brasaland-whisper-test"
    assert body["transcript"] == ORDER

    monkeypatch.setattr(
        "services.concierge.transcribe.transcribe_with_model",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )
    # resolve_transcript calls transcribe_with_model which raises AudioModelError only
    # from the real client. Force that error type.
    from services.concierge.transcribe import AudioModelError

    def _down(*_args, **_kwargs):
        raise AudioModelError("down")

    monkeypatch.setattr("services.concierge.transcribe.transcribe_with_model", _down)
    failed = client.post(
        "/concierge/transcribe",
        files={"audio": ("order.webm", b"voice-bytes", "audio/webm")},
    )
    assert failed.status_code == 503
    assert "sk-" not in failed.text
    assert "test-audio-key" not in failed.text


def test_transcribe_request_builds_without_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real client targets the configured model and does not run in unit tests."""
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"text":"one corn arepa at Orlando"}'

    def _urlopen(request, timeout=30):
        captured["url"] = request.full_url
        captured["auth"] = request.headers["Authorization"]
        captured["body"] = request.data
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setenv("BRASALAND_AUDIO_API_KEY", "test-audio-key")
    monkeypatch.setenv("BRASALAND_AUDIO_MODEL", "brasaland-whisper-test")
    monkeypatch.setenv("BRASALAND_AUDIO_BASE_URL", "https://audio.example.test/v1")
    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    text = transcribe_with_model(b"abc", "order.wav", "audio/wav")
    assert text == "one corn arepa at Orlando"
    assert captured["url"] == "https://audio.example.test/v1/audio/transcriptions"
    assert captured["auth"] == "Bearer test-audio-key"
    assert b"brasaland-whisper-test" in captured["body"]
    assert b"order.wav" in captured["body"]


def test_openapi_keeps_menu_location_sales_and_adds_concierge_streams() -> None:
    paths = app.openapi()["paths"]
    assert "/concierge/sessions" in paths
    assert "/concierge/transcribe" in paths
    assert "/realtime/concierge/stream" in paths
    assert "/realtime/ops-alerts/stream" in paths
    assert "/menus" in paths
    assert "/locations" in paths
    assert "/sales" in paths
    assert any(getattr(route, "path", "") == "/concierge/ws" for route in concierge_router.routes)
    assert any(getattr(route, "path", "") == "/knowledge/ws" for route in knowledge_router.routes)
