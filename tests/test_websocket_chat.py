"""WebSocket chat for Brasaland manager_support."""

from __future__ import annotations

import asyncio
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
from data.pipelines.rag import answer_question, query_stream  # noqa: E402
from services.knowledge.chat import (  # noqa: E402
    PART1_EVENT_NAMES,
    hub,
    producers,
    reset_chat_state,
    store,
    token_event,
)
import users  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("BRASALAND_RAG_BACKEND", "local")
    monkeypatch.setenv("BRASALAND_RAG_EMBEDDINGS", "local")
    monkeypatch.setenv("BRASALAND_RAG_LLM", "extractive")
    monkeypatch.setattr(users, "DATABASE_PATH", tmp_path / "company_api.db")
    reset_chat_state()
    yield
    reset_chat_state()


def _token(client: TestClient) -> str:
    response = client.post(
        "/auth/register",
        json={
            "email": "mariana.chat@brasaland.test",
            "password": "secret-password",
            "name": "Mariana Restrepo",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _session(client: TestClient, token: str) -> str:
    created = client.post("/knowledge/sessions", headers={"Authorization": f"Bearer {token}"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["session_id"].startswith("BRS-CHAT-")
    assert body["thread_id"] == body["session_id"]
    assert body["company"] == "brasaland"
    assert body["agent_id"] == "manager_support"
    assert body["status"] == "idle"
    assert body["messages"] == []
    return body["session_id"]


def test_query_stream_matches_the_full_answer_in_message_sized_deltas() -> None:
    question = "What does the House Sauce contain?"
    pieces = list(query_stream(question))
    assert len(pieces) > 1
    assert "".join(pieces) == answer_question(question)["answer"]


def test_sessions_and_stream_require_the_staff_jwt() -> None:
    client = TestClient(app)
    assert client.post("/knowledge/sessions").status_code == 401
    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect("/knowledge/ws?token=not-a-jwt&session_id=BRS-CHAT-000001") as socket:
            socket.receive_json()
    assert caught.value.code == 4401


def test_unknown_thread_closes_before_a_session_event() -> None:
    client = TestClient(app)
    token = _token(client)
    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect(
            f"/knowledge/ws?token={token}&session_id=BRS-CHAT-000099"
        ) as socket:
            socket.receive_json()
    assert caught.value.code == 4404


def test_stream_emits_token_chunks_and_restores_the_thread() -> None:
    client = TestClient(app)
    token = _token(client)
    session_id = _session(client, token)
    question = "What is the capital of Japan?"
    with client.websocket_connect(
        f"/knowledge/ws?token={token}&thread_id={session_id}"
    ) as socket:
        hello = socket.receive_json()
        assert hello["event"] == "support_session"
        assert hello["agent_id"] == "manager_support"
        assert hello["messages"] == []
        socket.send_json({"event": "support_user_message", "content": question})
        frames = []
        while True:
            frame = socket.receive_json()
            frames.append(frame)
            if frame["event"] == "support_assistant_message":
                break
    events = [frame["event"] for frame in frames]
    assert "token_chunk" in events
    assert "knowledge_token" not in events
    assert events[-1] == "support_assistant_message"
    assert "message" not in events
    assert PART1_EVENT_NAMES.isdisjoint(events)
    done = frames[-1]
    assert done["status"] == "complete"
    assert done["session_id"] == session_id
    assert done["thread_id"] == session_id
    assert "not enough information" in done["content"].lower()
    deltas = "".join(frame["delta"] for frame in frames if frame["event"] == "token_chunk")
    assert deltas == done["content"]

    with client.websocket_connect(
        f"/knowledge/ws?token={token}&session_id={session_id}"
    ) as socket:
        restored = socket.receive_json()
    assert restored["event"] == "support_session"
    assert restored["session_id"] == session_id
    assert [row["role"] for row in restored["messages"]] == ["user", "assistant"]
    assert restored["messages"][0]["content"] == question
    assert restored["messages"][1]["content"] == done["content"]


def test_interrupt_stops_the_token_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRASALAND_CHAT_TOKEN_DELAY", "0.05")
    client = TestClient(app)
    token = _token(client)
    session_id = _session(client, token)
    with client.websocket_connect(
        f"/knowledge/ws?token={token}&session_id={session_id}"
    ) as socket:
        assert socket.receive_json()["event"] == "support_session"
        socket.send_json(
            {
                "event": "support_user_message",
                "content": "What does the House Sauce contain?",
            }
        )
        saw_token = False
        final = None
        while final is None:
            frame = socket.receive_json()
            if frame["event"] == "token_chunk" and not saw_token:
                saw_token = True
                socket.send_json({"event": "support_interrupt"})
            if frame["event"] == "support_assistant_message":
                final = frame
    assert saw_token
    assert final is not None
    assert final["status"] == "interrupted"
    assert final["content"]
    full = answer_question("What does the House Sauce contain?")["answer"]
    assert len(final["content"]) < len(full)
    assert final["event"] == "support_assistant_message"


def test_two_subscribers_receive_the_same_token_chunk() -> None:
    async def scenario() -> None:
        session_id = store.create()["session_id"]
        first = hub.subscribe(session_id)
        second = hub.subscribe(session_id)
        await hub.publish(session_id, token_event(session_id, "Brasa"))
        assert first.get_nowait() == {
            "event": "token_chunk",
            "session_id": session_id,
            "thread_id": session_id,
            "delta": "Brasa",
        }
        assert second.get_nowait()["delta"] == "Brasa"
        hub.unsubscribe(session_id, first)
        producer = producers.get(session_id, store, hub)
        await producer.start_turn("What is the capital of Japan?")
        assert producer._task is not None
        await producer._task
        saved = store.get(session_id)
        assert saved is not None
        assert saved["status"] == "idle"
        assert saved["agent_id"] == "manager_support"
        assert "not enough information" in saved["messages"][-1]["content"].lower()

    asyncio.run(scenario())
