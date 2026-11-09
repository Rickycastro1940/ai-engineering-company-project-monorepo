"""Llama Guard-style rails for Brasaland Groq agents.

NeMo Guardrails would add a separate runtime and config stack. This module
keeps the existing plain-Python Groq loop and uses Llama Guard's contract
instead: a ``safe`` / ``unsafe`` verdict plus category codes.

* ``S1`` — not restaurant operations
* ``S2`` — proprietary supplier data (negotiated prices, contract terms,
  margins, payment details)

The policy runs locally so the agent still answers with no extra services
and no API keys. Set ``BRASALAND_LLAMA_GUARD_MODEL`` (a Groq-hosted Llama
Guard id) to add a model verdict on text the local policy already marked
safe. A model failure leaves the local verdict in place.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

REFUSAL_OFF_TOPIC = (
    "I can only help with Brasaland restaurant operations: inventory, kitchens, "
    "menus, locations, in-service sales, recipes, waste, allergens, and shift prep."
)
REFUSAL_SUPPLIER = (
    "I can't share proprietary supplier data: negotiated prices, contract terms, "
    "margins, or payment details. Procurement keeps those records."
)

_PROPRIETARY = re.compile(
    r"negotiated\s+(price|rate|discount|term)s?"
    r"|contract\s+(price|rate|terms|value)"
    r"|supplier(?:'s|s)?\s+(price|pricing|rate|margin|bank|iban|account)"
    r"|(price|pricing|rate|margin|bank\s+account|iban)\s+of\s+the\s+supplier"
    r"|unit\s+cost\s+from\s+(the\s+)?supplier"
    r"|confidential\s+(supplier\s+)?(price|pricing|rate|terms)"
    r"|bank\s+account"
    r"|routing\s+number"
    r"|\biban\b"
    r"|precio\s+negociado"
    r"|tarifa\s+(del|de\s+la)\s+proveedor"
    r"|cuenta\s+bancaria"
    r"|margen\s+(del|de\s+la)\s+proveedor"
    r"|contrato\s+con\s+(el|la)\s+proveedor"
    r"|datos\s+bancarios"
    r"|costo\s+unitario\s+(del|de\s+la)\s+proveedor",
    re.IGNORECASE,
)
_PROPRIETARY_AMOUNT = re.compile(
    r"(supplier|proveedor|negotiated|contrato|contract).{0,80}"
    r"(\d[\d.,]*\s*(cop|usd)|\$\s?\d)"
    r"|(\d[\d.,]*\s*(cop|usd)|\$\s?\d).{0,80}(supplier|proveedor)",
    re.IGNORECASE | re.DOTALL,
)
_OFF_TOPIC = re.compile(
    r"\b(poem|poetry|poema|homework|calculus|c[aá]lculo|president|presidente|"
    r"bitcoin|crypto|celebrity|world\s+cup|mundial|weapon|exploit)\b"
    r"|medical\s+(diagnosis|prescription)"
    r"|diagn[oó]stico\s+m[eé]dico"
    r"|stock\s+market"
    r"|bolsa\s+de\s+valores"
    r"|ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions"
    r"|ignora\s+las\s+instrucciones"
    r"|write\s+(me\s+)?(some\s+)?(python|javascript|code)\b"
    r"|escribe\s+un\s+script",
    re.IGNORECASE,
)
_PROPRIETARY_KEYS = {
    "supplier_price",
    "unit_price",
    "unit_cost",
    "negotiated_price",
    "negotiated_rate",
    "contract_price",
    "contract_terms",
    "contract_rate",
    "bank_account",
    "iban",
    "routing_number",
    "margin",
    "margin_percent",
    "precio_negociado",
    "cuenta_bancaria",
    "costo_unitario",
}
_SUPPLIER_CONTEXT_KEYS = {"supplier", "suppliers", "proveedor", "proveedores"}
_SUPPLIER_VALUE_KEYS = {"price", "pricing", "cost", "rate", "amount", "terms", "margin"}

_LLAMA_GUARD_SYSTEM = """You are Llama Guard for Brasaland restaurant operations.
Classify the message. Categories:
S1: Off-topic. Not restaurant operations (inventory, kitchens, menus, locations, in-service sales, recipes, waste, allergens, shift prep).
S2: Proprietary supplier data. Negotiated prices, contract terms, margins, bank or payment details.

Reply with exactly one of:
safe
unsafe
S1
unsafe
S2
"""


@dataclass(frozen=True)
class GuardrailDecision:
    """Llama Guard verdict. ``llama_guard_text`` matches the model output shape."""

    allowed: bool
    verdict: str
    categories: tuple[str, ...]
    refusal: str
    source: str

    def llama_guard_text(self) -> str:
        if self.allowed:
            return "safe"
        lines = ["unsafe", *self.categories]
        return "\n".join(lines)


@dataclass(frozen=True)
class RemoteGuardResult:
    decision: GuardrailDecision
    model: str
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


def _allow(source: str = "llama-guard-policy") -> GuardrailDecision:
    return GuardrailDecision(
        allowed=True,
        verdict="safe",
        categories=(),
        refusal="",
        source=source,
    )


def _block(category: str, refusal: str, source: str) -> GuardrailDecision:
    return GuardrailDecision(
        allowed=False,
        verdict="unsafe",
        categories=(category,),
        refusal=refusal,
        source=source,
    )


def is_proprietary_supplier_text(text: str) -> bool:
    if not text:
        return False
    return _PROPRIETARY.search(text) is not None or _PROPRIETARY_AMOUNT.search(text) is not None


def is_off_topic(text: str) -> bool:
    if not text:
        return False
    return _OFF_TOPIC.search(text) is not None


def apply_llama_guard_policy(text: str, *, role: str = "user") -> GuardrailDecision:
    """Classify ``text`` with the local Llama Guard policy.

    ``role`` is ``user`` or ``assistant``. Both directions use the same
    categories so a model answer cannot leak what the user was refused.
    """
    del role  # same categories for user input and assistant output
    if is_proprietary_supplier_text(text):
        return _block("S2", REFUSAL_SUPPLIER, "llama-guard-policy")
    if is_off_topic(text):
        return _block("S1", REFUSAL_OFF_TOPIC, "llama-guard-policy")
    return _allow()


def moderate_latest_user_message(messages: list[dict[str, Any]]) -> GuardrailDecision:
    """Run the local policy on the newest user turn."""
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content") or ""
            return apply_llama_guard_policy(str(content), role="user")
    return _allow()


def scrub_supplier_payload(value: Any, *, supplier_context: bool = False) -> Any:
    """Drop proprietary supplier fields before they reach the model or the log."""
    if isinstance(value, dict):
        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            lowered = str(key).strip().lower()
            in_supplier = supplier_context or lowered in _SUPPLIER_CONTEXT_KEYS
            if lowered in _PROPRIETARY_KEYS or (in_supplier and lowered in _SUPPLIER_VALUE_KEYS):
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = scrub_supplier_payload(item, supplier_context=in_supplier)
        return cleaned
    if isinstance(value, list):
        return [scrub_supplier_payload(item, supplier_context=supplier_context) for item in value]
    if isinstance(value, str) and is_proprietary_supplier_text(value):
        return "[redacted proprietary supplier data]"
    return value


def parse_llama_guard_output(text: str) -> GuardrailDecision:
    """Parse a Llama Guard reply. Unrecognized text stays safe (local policy still ran)."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines or lines[0].lower() != "unsafe":
        return _allow("llama-guard-model")
    categories = tuple(line for line in lines[1:] if line) or ("S1",)
    supplier = any(item.upper().startswith("S2") or "supplier" in item.lower() for item in categories)
    if supplier:
        return _block("S2", REFUSAL_SUPPLIER, "llama-guard-model")
    return _block("S1", REFUSAL_OFF_TOPIC, "llama-guard-model")


def _usage_triplet(response: Any) -> tuple[int | None, int | None, int | None]:
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

    return (
        _get("prompt_tokens", "input_tokens", "input"),
        _get("completion_tokens", "output_tokens", "output"),
        _get("total_tokens", "total"),
    )


def classify_with_llama_guard(client: Any, text: str, role: str) -> RemoteGuardResult | None:
    """Call Groq-hosted Llama Guard when ``BRASALAND_LLAMA_GUARD_MODEL`` is set.

    Returns ``None`` when the model is not configured or the call fails, so
    the local policy remains the rail that always runs.
    """
    model = os.getenv("BRASALAND_LLAMA_GUARD_MODEL", "").strip()
    if not model or client is None:
        return None
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": _LLAMA_GUARD_SYSTEM},
                {"role": "user", "content": f"Role: {role}\nContent:\n{text}"},
            ],
        )
        content = response.choices[0].message.content or ""
    except Exception:
        return None
    latency_ms = (time.perf_counter() - started) * 1000
    prompt_tokens, completion_tokens, total_tokens = _usage_triplet(response)
    return RemoteGuardResult(
        decision=parse_llama_guard_output(content),
        model=model,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
