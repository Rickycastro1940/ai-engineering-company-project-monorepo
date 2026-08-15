# Brasaland — Agentic RFP Workflow

| Part | Focus | Status |
| ---- | ----- | ------ |
| **1 of 3** | Intake & Routing | Implemented |
| **2 of 3** | Response generation | Implemented |
| **3 of 3** | Approval + final document | Implemented (`data/pipelines/rfp_approval/`) |

## CONTEXT

Departments, owners, RFP format, arbitration, and seed PDFs: [`CONTEXT-company.md`](../../CONTEXT-company.md) (Milestone 9).  
Curriculum PDFs: [`rfp-requests/brasaland/`](../../rfp-requests/brasaland/).

**Part 3 sign-off (do not invent extra hierarchy):** each *active* department is approved by its named §2.1 owner (Camila Ospina, Felipe Guerrero, Lucía Fernández, Jake Morrison). Mariana Restrepo (CEO) is required only when estimated annual value exceeds USD $50,000.

**§7 arbitration** is a dedicated graph node with fixed trigger ids (`cost-vs-feasibility`, `setup-sla-breach`, `ceo-threshold`) — not LLM consensus.

**Part 3 HITL:** each pending department is a parallel `Send` branch; `interrupt()` pauses only that branch. Already-decided departments are not sent and are not blocked. A human decision is validated (`approve` / `reject` / `request_changes` and the named owner) then resumes that branch into `apply_approval` on the existing checkpoint — it does not restart from `load_handoff`.

**Completion:** while any department approval is pending, the ticket status is
`waiting_for_approval` and `GET .../final-document` is unavailable. Once every
active department has approved (and CEO when required), the synthesizer stores
the consolidated FinalDocument, sets status to `done`, and the document is
accessible. Details: [`data/pipelines/rfp_approval/COMPLETION.md`](../../data/pipelines/rfp_approval/COMPLETION.md).

**Cross-part continuity:** same `ticket_id` / `departments_needed` / metadata.
`GET /tickets/{id}` exposes `terminal` (= Part 1 intake finished) and
`pipeline_complete` (`done` / `discarded` / `failed`). Exhausted Part 2 drafts
keep section `approval_status=pending` for Part 3 HITL. Mid-Part-2 tickets
(`drafting` / `under_evaluation`) can resume generate without a status jump.

## Layout

| Piece | Location |
| ----- | -------- |
| Pipeline (Part 1) | `data/pipelines/rfp_intake/` |
| Pipeline (Part 2) | `data/pipelines/rfp_response/` |
| Pipeline (Part 3) | `data/pipelines/rfp_approval/` |
| HTTP (thin) | `services/rfp/` on `services.agent.app` (same process as agent) |
| Upload / ticket UI | `uis/backoffice/rfp-upload.html` (per-department approve / reject on the same ticket) |
| Approval UI | `uis/backoffice/rfp-approvals.html` |
| CLI | `scripts/rfp_intake_smoke.py` · `scripts/rfp_response_smoke.py` · `scripts/rfp_approval_smoke.py` · `scripts/rfp_part3_e2e_simulated_approvals.py` |
| Stored uploads | `data/raw/rfp/<ticket_id>/` |

## API

- `POST /rfp/tickets` — multipart upload; returns `analyzing` (or sync result when `RFP_INTAKE_SYNC=1`)
- `GET /rfp/tickets/{ticket_id}` — poll until `intake_complete` / `discarded` / `failed` / Part 2–3 statuses
- `POST /rfp/upload` — alias for tickets (backoffice)
- `POST /rfp/tickets/{ticket_id}/generate-response` — Part 2: consume Part 1 handoff, draft + evaluate
- `POST /rfp/tickets/{ticket_id}/start-approval` — Part 3: HITL pause for named owners (+ CEO if required)
- `POST /rfp/tickets/{ticket_id}/approvals` — `{department_id, decision, approver}` (`approved` / `rejected` / `request_changes`)
- `GET /rfp/tickets/{ticket_id}/final-document` — CONTEXT §2.3 FinalDocument after `done`
- `GET /rfp/part3/queue` — tickets in `waiting_for_approval` / `needs_human_review`

```bash
uv run uvicorn services.agent.app:app --reload --port 8000
# open http://127.0.0.1:8000/rfp-upload.html and /rfp-approvals.html
export RFP_INTAKE_SYNC=1 RFP_ALLOW_SQLITE=1
# Optional: RFP_CHECKPOINT_SQLITE=/tmp/rfp-approval-checkpoints.sqlite
uv run python scripts/rfp_intake_smoke.py
uv run python scripts/rfp_response_smoke.py
uv run python scripts/rfp_approval_smoke.py
# End-to-end (intake → generation → approval → completion on one ticket):
RFP_INTAKE_SYNC=1 RFP_ALLOW_SQLITE=1 uv run pytest tests/pipelines/test_rfp_e2e_full_pipeline.py -q
# Part 3 only — fixture + simulated programmatic approvals (no UI clicks):
RFP_ALLOW_SQLITE=1 uv run python scripts/rfp_part3_e2e_simulated_approvals.py --mode sequential
RFP_ALLOW_SQLITE=1 uv run pytest tests/pipelines/test_rfp_part3_simulated_approvals_e2e.py -q
uv run pytest tests/pipelines/test_rfp_*.py
```
