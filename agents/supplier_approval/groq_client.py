"""Optional Groq rewrite for the operations summary.

Uses the same OpenAI-compatible Groq client as root `agent.py`. The structured
decision stays on the deterministic handoff. Set `BRASALAND_SUPPLIER_AGENTS=groq`
and `GROQ_API_KEY` to ask Groq to phrase the summary. Any failure keeps the
original text.
"""

from __future__ import annotations

import os

from services.safe_errors import looks_sensitive


def maybe_refine_summary(summary: str, decision: str) -> tuple[str, str]:
    mode = os.getenv("BRASALAND_SUPPLIER_AGENTS", "deterministic").strip().lower()
    key = os.getenv("GROQ_API_KEY", "")
    if mode != "groq" or not key or key == "your_key_here":
        return summary, "not_used"
    locked = f"Decision: {decision}"
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=key,
            base_url="https://api.groq.com/openai/v1",
            timeout=30.0,
        )
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write a short supplier-approval note for Brasaland management. "
                        "Keep COP and USD as given. Do not invent standards, prices, or locations. "
                        f"The first line of your reply must be exactly `{locked}`."
                    ),
                },
                {"role": "user", "content": summary},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception:
        return summary, "unavailable"
    if not text.startswith(locked) or looks_sensitive(text):
        return summary, "unavailable"
    return text, "used"
