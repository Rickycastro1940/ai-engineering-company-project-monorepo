# Brasaland — Agentic RFP Workflow

| Part | Focus | Status |
| ---- | ----- | ------ |
| **1 of 3** | Intake & Routing | Implemented |
| **2 of 3** | Response generation | Implemented (`feature/rfp-response-generation`) |
| 3 of 3 | Approval + final document | — |

## CONTEXT

Departments, RFP format, persistence, and seed PDFs: [`CONTEXT-company.md`](../../CONTEXT-company.md) (Milestone 9 section).  
Curriculum PDFs: [`rfp-requests/brasaland/`](../../rfp-requests/brasaland/).

## Layout

| Piece | Location |
| ----- | -------- |
| Pipeline (Part 1) | `data/pipelines/rfp_intake/` |
| Pipeline (Part 2) | `data/pipelines/rfp_response/` |
| HTTP (thin) | `services/rfp/` on `services.agent.app` (same process as agent) |
| Upload UI | `uis/backoffice/rfp-upload.html` |
| CLI | `uv run python scripts/rfp_intake_smoke.py` · `uv run python scripts/rfp_response_smoke.py` |
| Stored uploads | `data/raw/rfp/<ticket_id>/` |

## API

- `POST /rfp/tickets` — multipart upload; returns `analyzing` (or sync result when `RFP_INTAKE_SYNC=1`)
- `GET /rfp/tickets/{ticket_id}` — poll until `intake_complete` / `discarded` / `failed` / Part 2 statuses
- `POST /rfp/upload` — alias for tickets (backoffice)
- `POST /rfp/tickets/{ticket_id}/generate-response` — Part 2: consume Part 1 handoff, draft + evaluate, persist drafts/evals (same API)

```bash
uv run uvicorn services.agent.app:app --reload --port 8000
# open http://127.0.0.1:8000/rfp-upload.html
export RFP_INTAKE_SYNC=1 RFP_ALLOW_SQLITE=1
uv run python scripts/rfp_intake_smoke.py
uv run python scripts/rfp_response_smoke.py
uv run pytest tests/pipelines/test_rfp_*.py
```
