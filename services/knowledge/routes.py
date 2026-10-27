"""Knowledge query and the WebSocket that streams the same assistant.

``POST /knowledge/query`` still returns one full answer. ``WS /knowledge/ws``
streams that answer as ``knowledge_token`` events so a staff member can
interrupt a reply that is going the wrong way.

Mounted from ``services/api/app.py`` (the app ``uvicorn api.app:app`` loads).
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from data.pipelines.rag import answer_question
from services.knowledge.chat import store
from services.knowledge.socket import run_knowledge_websocket
from users import get_current_user

logger = logging.getLogger("brasaland.knowledge")

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
UI_PAGE = Path(__file__).resolve().parents[2] / "uis" / "knowledge" / "index.html"


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class SourceChunk(BaseModel):
    source_document: str
    section: str
    text: str
    score: float
    chunk_index: int
    language: str = "en"


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]


@router.post("/query", response_model=QueryResponse)
def query_knowledge_base(payload: QueryRequest) -> QueryResponse:
    """Answer from Brasaland knowledge documents and return the cited chunks."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    result = answer_question(question)
    logger.info("knowledge_query sources=%d", len(result["sources"]))
    return QueryResponse(**result)


@router.post("/sessions", status_code=201)
def create_chat_session(_user: dict = Depends(get_current_user)) -> dict:
    """Open a conversation thread. The WebSocket does not create one."""
    return store.create()


@router.get("/sessions/{session_id}")
def read_chat_session(session_id: str, _user: dict = Depends(get_current_user)) -> dict:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.websocket("/ws")
async def knowledge_chat_socket(websocket: WebSocket) -> None:
    await run_knowledge_websocket(websocket)


@router.get("/chat.js", include_in_schema=False)
def knowledge_chat_script() -> FileResponse:
    script = UI_PAGE.with_name("chat.js")
    if not script.is_file():
        raise HTTPException(status_code=404, detail="Knowledge chat script is not installed")
    return FileResponse(script, media_type="text/javascript")


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
@router.get("/ui", include_in_schema=False)
def knowledge_chat_page() -> FileResponse:
    if not UI_PAGE.is_file():
        raise HTTPException(status_code=404, detail="Knowledge chat page is not installed")
    return FileResponse(UI_PAGE)
