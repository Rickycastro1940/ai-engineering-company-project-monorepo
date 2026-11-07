# Groq LLMOps

Shared tracing and guardrails for the Brasaland inventory agent (`agent.py`). Department: **Technology** (Nicolás Park — telemetry on the assistant path). The rail also keeps Operations answers inside restaurant work and blocks Procurement’s proprietary supplier terms.

## Tracing (Langfuse)

Each Groq `chat.completions` call records latency and token usage. `/feedback up|down [comment]` writes a `user-feedback` score on the latest turn.

| Variable | Role |
| --- | --- |
| `LANGFUSE_PUBLIC_KEY` | Ingestion username. Missing or `your_key_here` → no network call |
| `LANGFUSE_SECRET_KEY` | Ingestion password |
| `LANGFUSE_HOST` or `LANGFUSE_BASE_URL` | Default `https://cloud.langfuse.com` |

The client posts to `{host}/api/public/ingestion` with the standard library. No Langfuse package. Without both keys the same records stay in memory so the agent still runs.

Phoenix is not used: it needs a collector process. Langfuse is one optional HTTPS endpoint.

## Guardrails (Llama Guard contract)

Local policy, always on:

| Code | Blocks |
| --- | --- |
| `S1` | Questions and answers that are not restaurant operations |
| `S2` | Proprietary supplier data: negotiated prices, contract terms, margins, payment details |

`BRASALAND_LLAMA_GUARD_MODEL` (for example a Groq-hosted Llama Guard id) adds a model check on text the local policy already marked safe. If that call fails, the local verdict stands.

NeMo Guardrails is not used: it is a separate runtime, and this loop stays plain Python around the Groq client.

```bash
python3 -m pytest tests/test_llmops.py -q
```
