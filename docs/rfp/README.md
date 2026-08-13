# Brasaland — Agentic RFP Workflow

| Part | Focus | Status |
| ---- | ----- | ------ |
| **1 of 3** | Intake & Routing | Implemented |
| 2 of 3 | Response generation | — |
| 3 of 3 | Approval + final document | — |

## CONTEXT

Departments, RFP format, persistence, and seed PDFs: [`CONTEXT-company.md`](../../CONTEXT-company.md) (Milestone 9 section).  
Curriculum PDFs: [`rfp-requests/brasaland/`](../../rfp-requests/brasaland/).

## Layout

| Piece | Location |
| ----- | -------- |
| Pipeline | `data/pipelines/rfp_intake/` |
| HTTP (thin) | `services/rfp/` on `services.agent.app` (same process as agent) |
| Upload UI | `uis/backoffice/rfp-upload.html` |
| CLI | `uv run python scripts/rfp_intake_smoke.py` |
| Stored uploads | `data/raw/rfp/<ticket_id>/` |

## API

- `POST /rfp/tickets` — multipart upload; returns `analyzing` (or sync result when `RFP_INTAKE_SYNC=1`)
- `GET /rfp/tickets/{ticket_id}` — poll until `intake_complete` / `discarded` / `failed`
- `POST /rfp/upload` — alias for tickets (backoffice)

```bash
uv run uvicorn services.agent.app:app --reload --port 8000
# open http://127.0.0.1:8000/rfp-upload.html
uv run python scripts/rfp_intake_smoke.py
```
