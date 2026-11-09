"""Voice orders through an env-configured transcription model.

``BRASALAND_AUDIO_API_KEY`` selects the model. When it is unset the concierge
accepts the order as text and does not call the network.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import uuid

logger = logging.getLogger("brasaland.concierge.audio")

AUDIO_KEY_ENV = "BRASALAND_AUDIO_API_KEY"
AUDIO_MODEL_ENV = "BRASALAND_AUDIO_MODEL"
AUDIO_BASE_ENV = "BRASALAND_AUDIO_BASE_URL"
DEFAULT_MODEL = "whisper-1"
DEFAULT_BASE = "https://api.openai.com/v1"
FALLBACK_DETAIL = "No audio key is set. Type the order instead."


class AudioModelError(RuntimeError):
    """The configured transcription model could not be reached."""


def audio_configured() -> bool:
    return bool(os.getenv(AUDIO_KEY_ENV, "").strip())


def configured_model() -> str:
    return os.getenv(AUDIO_MODEL_ENV, "").strip() or DEFAULT_MODEL


def transcribe_with_model(audio: bytes, filename: str, content_type: str) -> str:
    """POST audio to an OpenAI-compatible ``/audio/transcriptions`` endpoint."""
    key = os.getenv(AUDIO_KEY_ENV, "").strip()
    if not key:
        raise AudioModelError(FALLBACK_DETAIL)
    model = configured_model()
    base = os.getenv(AUDIO_BASE_ENV, "").strip() or DEFAULT_BASE
    boundary = f"----brasaland{uuid.uuid4().hex}"
    file_name = filename or "order.webm"
    mime = content_type or "application/octet-stream"
    parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="model"\r\n\r\n',
        model.encode(),
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode(),
        audio,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    request = urllib.request.Request(
        f"{base.rstrip('/')}/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        logger.warning("audio transcription failed")
        raise AudioModelError("The audio model is unavailable.") from error
    text = str(payload.get("text") or "").strip()
    if not text:
        raise AudioModelError("The audio model returned an empty transcript.")
    return text


def resolve_transcript(
    *,
    text: str = "",
    audio: bytes | None = None,
    filename: str = "",
    content_type: str = "",
) -> dict[str, str | bool | None]:
    """Transcribe audio when a key is set. Otherwise return the typed order."""
    typed = (text or "").strip()
    configured = audio_configured()
    if audio and configured:
        transcript = transcribe_with_model(audio, filename, content_type)
        return {
            "transcript": transcript,
            "mode": "model",
            "model": configured_model(),
            "audio_configured": True,
            "detail": "",
        }
    if typed:
        return {
            "transcript": typed,
            "mode": "text_fallback" if not configured else "text",
            "model": configured_model() if configured else None,
            "audio_configured": configured,
            "detail": "" if configured else FALLBACK_DETAIL,
        }
    if audio and not configured:
        return {
            "transcript": "",
            "mode": "text_fallback",
            "model": None,
            "audio_configured": False,
            "detail": FALLBACK_DETAIL,
        }
    return {
        "transcript": "",
        "mode": "text_fallback",
        "model": None,
        "audio_configured": configured,
        "detail": "Send text, or audio when an audio key is configured.",
    }
