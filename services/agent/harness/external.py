"""Isolate and sanitize untrusted external text (RAG docs + tool outputs).

Retrieved knowledge-base chunks and external tool payloads are **DATA**.
They must never be concatenated into the system role or obeyed as instructions.
"""

from __future__ import annotations

import re
from typing import Any

from services.agent.harness.restrictions import looks_like_jailbreak

# Delimiters — user/tool/RAG roles only. Never placed in the system message.
UNTRUSTED_RAG_OPEN = "<untrusted_rag_document>"
UNTRUSTED_RAG_CLOSE = "</untrusted_rag_document>"
UNTRUSTED_TOOL_OPEN = "<untrusted_tool_output>"
UNTRUSTED_TOOL_CLOSE = "</untrusted_tool_output>"
UNTRUSTED_MEMORY_OPEN = "<untrusted_memory_record>"
UNTRUSTED_MEMORY_CLOSE = "</untrusted_memory_record>"

# Marker left after neutralizing instruction-change phrases inside external text.
NEUTRALIZED_INSTRUCTION_MARKER = (
    "[untrusted external text: instruction-like phrase removed]"
)

_DELIMITER_TAGS = re.compile(
    r"</?(?:untrusted_rag_document|untrusted_tool_output|untrusted_memory_record|"
    r"untrusted_user_input)>",
    re.IGNORECASE,
)

# Same family as jailbreak / instruction-change — neutralized inside RAG/tool text.
_INSTRUCTION_LIKE_IN_EXTERNAL = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above|your)\s+"
    r"(instructions|rules|prompt|guidelines)"
    r"|you\s+are\s+now\s+(an?\s+)?(assistant|ai|bot|model).{0,40}no\s+"
    r"(rules|restrictions|guidelines)"
    r"|you\s+are\s+now\s+(dan|jailbroken|unrestricted)"
    r"|forget\s+that\s+you\s+work\s+for\s+(the\s+)?(company|brasaland)"
    r"|you\s+have\s+no\s+(rules|restrictions|guidelines|guardrails)"
    r"|jailbreak"
    r"|developer\s+mode"
    r"|system\s+prompt\s+override"
    r"|(reveal|show|print|dump|repeat)\s+(?:\w+\s+){0,4}(the\s+)?(system\s+)?"
    r"(prompt|instructions)"
    r"|pretend\s+you\s+have\s+no\s+(rules|restrictions|guardrails)"
    r"|^\s*system\s*:\s*"
    r"|\[(?:SYSTEM|INST)\]",
    re.IGNORECASE | re.MULTILINE,
)


def strip_delimiter_tags(text: str) -> str:
    """Remove wrapper tags so untrusted content cannot break out of isolation."""
    return _DELIMITER_TAGS.sub("", text or "")


def neutralize_instruction_like(text: str) -> str:
    """Replace instruction-change phrases inside external data with a marker."""
    return _INSTRUCTION_LIKE_IN_EXTERNAL.sub(NEUTRALIZED_INSTRUCTION_MARKER, text or "")


def sanitize_external_text(text: str) -> str:
    """Sanitize text from RAG documents or tools before any model prompt use."""
    cleaned = strip_delimiter_tags(text or "")
    return neutralize_instruction_like(cleaned)


def contains_instruction_injection(text: str) -> bool:
    """True when external text embeds an instruction-change / jailbreak phrase."""
    return looks_like_jailbreak(text) or bool(
        _INSTRUCTION_LIKE_IN_EXTERNAL.search(text or "")
    )


def wrap_untrusted_rag_document(body: str) -> str:
    """Isolate one retrieved document block as untrusted DATA."""
    safe = sanitize_external_text(body)
    return f"{UNTRUSTED_RAG_OPEN}\n{safe}\n{UNTRUSTED_RAG_CLOSE}"


def wrap_untrusted_tool_output(body: str) -> str:
    """Isolate external tool payload text as untrusted DATA."""
    safe = sanitize_external_text(body)
    return f"{UNTRUSTED_TOOL_OPEN}\n{safe}\n{UNTRUSTED_TOOL_CLOSE}"


def wrap_untrusted_memory_record(body: str) -> str:
    """Isolate a recalled memory row as untrusted DATA (not instructions)."""
    safe = sanitize_external_text(body)
    return f"{UNTRUSTED_MEMORY_OPEN}\n{safe}\n{UNTRUSTED_MEMORY_CLOSE}"


def sanitize_retrieved_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copies of RAG chunks with instruction-like text neutralized.

    Scores / payload keys are left for tracing but must never enter the
    user-facing answer (enforced by output guardrails).
    """
    cleaned: list[dict[str, Any]] = []
    for chunk in chunks or []:
        item = dict(chunk)
        item["text"] = sanitize_external_text(str(item.get("text") or ""))
        cleaned.append(item)
    return cleaned


def format_isolated_rag_context(chunks: list[dict[str, Any]] | str) -> str:
    """Format retrieved context as isolated untrusted documents for the user role.

    Never returns content intended for the system role.
    """
    if isinstance(chunks, str):
        body = (chunks or "").strip()
        if not body:
            return "(none)"
        return wrap_untrusted_rag_document(body)

    if not chunks:
        return "(none)"

    parts: list[str] = []
    for chunk in chunks:
        source = chunk.get("source_document", "unknown")
        text = chunk.get("text", "")
        block = f"source_document={source}\n{text}"
        parts.append(wrap_untrusted_rag_document(block))
    return "\n\n".join(parts)


def format_isolated_tool_payload(payload: dict[str, Any] | str | None) -> str:
    """Serialize and isolate an external tool result for prompt use."""
    if payload is None:
        return wrap_untrusted_tool_output("(none)")
    if isinstance(payload, str):
        return wrap_untrusted_tool_output(payload)
    # Keep a stable, readable dump without pretending it is instructions.
    lines: list[str] = []
    for key in sorted(payload.keys()):
        lines.append(f"{key}={payload.get(key)!r}")
    return wrap_untrusted_tool_output("\n".join(lines))
