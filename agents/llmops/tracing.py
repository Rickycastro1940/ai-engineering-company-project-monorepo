"""Langfuse tracing for Groq chat completions.

Arize Phoenix needs a running collector. Langfuse's public ingestion API is
one HTTPS POST, so this client uses the standard library and no extra
package. With ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` unset (or
still placeholders), every method records latency, token usage, and feedback
in memory and skips the network. The inventory agent keeps running.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from agents.llmops.guardrails import is_proprietary_supplier_text

logger = logging.getLogger("brasaland.llmops")

_PLACEHOLDERS = {"", "your_key_here", "changeme", "placeholder", "none", "null"}
_DEFAULT_HOST = "https://cloud.langfuse.com"

Poster = Callable[..., None]


class FeedbackError(ValueError):
    """The feedback hook was called without a trace or with an unknown rating."""


@dataclass
class GenerationRecord:
    trace_id: str
    generation_id: str
    name: str
    model: str
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    exported: bool
    error: str | None = None


@dataclass
class FeedbackRecord:
    trace_id: str
    name: str
    value: float
    comment: str
    exported: bool


@dataclass
class TraceRecord:
    trace_id: str
    name: str
    session_id: str | None
    user_input: str
    output: str | None = None
    exported: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)


def _usable_key(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() not in _PLACEHOLDERS


def _iso(moment: datetime | None = None) -> str:
    current = moment or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def redact_trace_text(text: str, limit: int = 8000) -> str:
    """Keep supplier commercial terms out of exported traces."""
    if not isinstance(text, str):
        text = str(text)
    if is_proprietary_supplier_text(text):
        return "[redacted proprietary supplier data]"
    if len(text) > limit:
        return text[:limit]
    return text


def redact_payload(value: Any) -> Any:
    if isinstance(value, str):
        return redact_trace_text(value)
    if isinstance(value, dict):
        return {key: redact_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_payload(item) for item in value]
    return value


def normalize_feedback_value(value: Any) -> float:
    """Map a user rating to a numeric Langfuse score (1 positive, 0 negative)."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value in (0, 1):
            return float(value)
    text = str(value).strip().lower()
    if text in {"up", "good", "yes", "true", "1", "thumbs_up", "positive"}:
        return 1.0
    if text in {"down", "bad", "no", "false", "0", "thumbs_down", "negative"}:
        return 0.0
    raise FeedbackError("Feedback must be up or down.")


def parse_feedback_command(text: str) -> tuple[str, str] | None:
    """Parse ``/feedback up|down [comment]``. Other lines return ``None``."""
    stripped = text.strip()
    if not stripped.lower().startswith("/feedback"):
        return None
    rest = stripped[len("/feedback") :].strip()
    if not rest:
        raise FeedbackError("Usage: /feedback up|down [comment]")
    value, _, comment = rest.partition(" ")
    normalize_feedback_value(value)
    return value, comment.strip()


def post_ingestion(
    *,
    url: str,
    payload: dict[str, Any],
    public_key: str,
    secret_key: str,
    timeout: float = 5.0,
) -> None:
    """POST one Langfuse ingestion batch. Basic auth, public key as username."""
    raw = json.dumps(payload).encode("utf-8")
    token = base64.b64encode(f"{public_key}:{secret_key}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


class LangfuseTracer:
    """Records Groq generations and a user-feedback score.

    ``poster`` is the HTTP sender. Tests pass a fake. The default posts to
    ``{host}/api/public/ingestion`` only when both keys are set.
    """

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str = _DEFAULT_HOST,
        poster: Poster | None = None,
    ) -> None:
        self.public_key = (public_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        self.host = (host or _DEFAULT_HOST).rstrip("/")
        self.enabled = _usable_key(self.public_key) and _usable_key(self.secret_key)
        self._poster = poster or post_ingestion
        self.traces: list[TraceRecord] = []
        self.generations: list[GenerationRecord] = []
        self.feedback: list[FeedbackRecord] = []
        self.last_trace_id: str | None = None

    @classmethod
    def from_env(cls, poster: Poster | None = None) -> LangfuseTracer:
        host = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL") or _DEFAULT_HOST
        return cls(
            os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            os.getenv("LANGFUSE_SECRET_KEY", ""),
            host,
            poster=poster,
        )

    def _export(self, event_type: str, body: dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        payload = {
            "batch": [
                {
                    "id": str(uuid.uuid4()),
                    "type": event_type,
                    "timestamp": _iso(),
                    "body": body,
                }
            ]
        }
        url = f"{self.host}/api/public/ingestion"
        try:
            self._poster(
                url=url,
                payload=payload,
                public_key=self.public_key,
                secret_key=self.secret_key,
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            logger.warning("langfuse export failed for %s", event_type)
            return False
        except Exception:
            logger.warning("langfuse export failed for %s", event_type)
            return False
        return True

    def start_trace(
        self,
        *,
        name: str,
        session_id: str | None,
        user_input: str,
    ) -> str:
        trace_id = str(uuid.uuid4())
        safe_input = redact_trace_text(user_input)
        record = TraceRecord(
            trace_id=trace_id,
            name=name,
            session_id=session_id,
            user_input=safe_input,
        )
        exported = self._export(
            "trace-create",
            {
                "id": trace_id,
                "timestamp": _iso(),
                "name": name,
                "sessionId": session_id,
                "input": safe_input,
                "metadata": {"company": "Brasaland", "provider": "groq"},
                "tags": ["brasaland", "groq"],
            },
        )
        record.exported = exported
        self.traces.append(record)
        self.last_trace_id = trace_id
        return trace_id

    def finish_trace(self, trace_id: str, output: str) -> None:
        safe_output = redact_trace_text(output)
        for record in self.traces:
            if record.trace_id == trace_id:
                record.output = safe_output
                record.exported = self._export(
                    "trace-create",
                    {
                        "id": trace_id,
                        "timestamp": _iso(),
                        "name": record.name,
                        "sessionId": record.session_id,
                        "input": record.user_input,
                        "output": safe_output,
                        "metadata": {"company": "Brasaland", "provider": "groq"},
                    },
                ) or record.exported
                return

    def record_generation(
        self,
        *,
        trace_id: str,
        name: str,
        model: str,
        started_at: datetime,
        ended_at: datetime,
        latency_ms: float,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        input_payload: Any = None,
        output: Any = None,
        error: str | None = None,
    ) -> GenerationRecord:
        generation_id = str(uuid.uuid4())
        body: dict[str, Any] = {
            "id": generation_id,
            "traceId": trace_id,
            "name": name,
            "startTime": _iso(started_at),
            "endTime": _iso(ended_at),
            "model": model,
            "input": redact_payload(input_payload),
            "output": redact_payload(output),
            "metadata": {
                "latency_ms": round(latency_ms, 3),
                "provider": "groq",
            },
        }
        if error:
            body["level"] = "ERROR"
            body["statusMessage"] = "language model is unavailable"
            body["metadata"]["error"] = "language model is unavailable"
        if None not in (prompt_tokens, completion_tokens, total_tokens):
            body["usage"] = {
                "input": prompt_tokens,
                "output": completion_tokens,
                "total": total_tokens,
                "unit": "TOKENS",
            }
        else:
            body["metadata"]["usage_missing"] = True
        exported = self._export("generation-create", body)
        record = GenerationRecord(
            trace_id=trace_id,
            generation_id=generation_id,
            name=name,
            model=model,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            exported=exported,
            error=error,
        )
        self.generations.append(record)
        return record

    def record_guardrail(
        self,
        trace_id: str,
        *,
        verdict: str,
        categories: tuple[str, ...],
        source: str,
        allowed: bool,
    ) -> None:
        body = {
            "id": str(uuid.uuid4()),
            "traceId": trace_id,
            "name": "llama-guard",
            "input": {"verdict": verdict, "categories": list(categories), "source": source},
            "output": {"allowed": allowed},
            "metadata": {"provider": "llama-guard"},
        }
        self._export("event-create", body)
        for record in self.traces:
            if record.trace_id == trace_id:
                record.events.append(body["input"])
                return

    def record_feedback(
        self,
        trace_id: str | None,
        value: Any,
        comment: str = "",
    ) -> FeedbackRecord:
        """Attach a user score to a trace. This is the feedback hook.

        ``trace_id`` defaults to the latest turn. ``value`` is ``up`` or
        ``down`` (also ``1`` / ``0``). The score name is ``user-feedback``.
        """
        target = trace_id or self.last_trace_id
        if not target:
            raise FeedbackError("No traced answer to attach feedback to.")
        numeric = normalize_feedback_value(value)
        score_id = str(uuid.uuid4())
        exported = self._export(
            "score-create",
            {
                "id": score_id,
                "traceId": target,
                "name": "user-feedback",
                "value": numeric,
                "comment": redact_trace_text(comment, limit=2000),
                "dataType": "NUMERIC",
            },
        )
        record = FeedbackRecord(
            trace_id=target,
            name="user-feedback",
            value=numeric,
            comment=comment,
            exported=exported,
        )
        self.feedback.append(record)
        return record


def usage_from_response(response: Any) -> tuple[int | None, int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None, None, None

    def _get(*names: str) -> int | None:
        for name in names:
            raw = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            if raw is None:
                continue
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
        return None

    prompt = _get("prompt_tokens", "input_tokens", "input")
    completion = _get("completion_tokens", "output_tokens", "output")
    total = _get("total_tokens", "total")
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    return prompt, completion, total


def observe_chat_completion(
    tracer: LangfuseTracer,
    trace_id: str,
    call: Callable[[], Any],
    *,
    model: str,
    name: str = "groq.chat.completions",
    input_payload: Any = None,
) -> Any:
    """Time one Groq chat call and store latency plus token usage."""
    started_at = datetime.now(timezone.utc)
    started = time_counter()
    try:
        response = call()
    except Exception:
        ended_at = datetime.now(timezone.utc)
        tracer.record_generation(
            trace_id=trace_id,
            name=name,
            model=model,
            started_at=started_at,
            ended_at=ended_at,
            latency_ms=(time_counter() - started) * 1000,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            input_payload=input_payload,
            output=None,
            error="language model is unavailable",
        )
        raise
    ended_at = datetime.now(timezone.utc)
    prompt_tokens, completion_tokens, total_tokens = usage_from_response(response)
    output_text: Any = None
    try:
        output_text = response.choices[0].message.content
    except (AttributeError, IndexError):
        output_text = None
    tracer.record_generation(
        trace_id=trace_id,
        name=name,
        model=model,
        started_at=started_at,
        ended_at=ended_at,
        latency_ms=(time_counter() - started) * 1000,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        input_payload=input_payload,
        output=output_text,
    )
    return response


def time_counter() -> float:
    """Monotonic clock. Split out so tests can stub latency if needed."""
    import time

    return time.perf_counter()
