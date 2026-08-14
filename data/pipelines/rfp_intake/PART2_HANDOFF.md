# Part 2 handoff contract (RFP intake → drafting)

Part 1 routes accepted tickets into the rest of the agentic flow **without a
second API process**. Routing uses **all** of:

| Mechanism | Where |
| --------- | ----- |
| **Queue flag** | `rfp_tickets.part2_ready` (indexed; selects Part 2 queue) |
| **DB field** | `rfp_tickets.part2_handoff_json` (full contract JSON) |
| **Documented contract** | this file + `routing.build_part2_handoff` / `validate_part2_handoff` |
| **Queue view** | tickets with `part2_ready=true` + `status=intake_complete` |
| **HTTP (same app)** | `GET /rfp/part2/queue`, `GET /rfp/tickets/{id}/part2-handoff` |

## Guarantee

Part 2 **must not re-parse the PDF**. Start from:

1. `ticket_id` (always present in the persisted handoff)
2. Synthesizer payload: `work_streams[]` each with `department_id`, `owner`, `key_aspects`, `open_questions`
   (plus top-level `synthesizer` block with `departments_for_drafting` / `owners` / `ask_whom`)

Evals: `tests/pipelines/test_rfp_part2_handoff_contract.py`, `tests/pipelines/test_rfp_routing.py`.


Markdown and metadata already live on the ticket row if needed for grounding;
`reparse_pdf_required` is always `false` in a valid contract.

## Contract shape (`schema_version: "1.0"`)

```json
{
  "schema_version": "1.0",
  "ticket_id": "<uuid hex>",
  "status": "intake_complete",
  "part2_ready": true,
  "routed_at": "2026-08-13T00:00:00Z",
  "next_part": 2,
  "reparse_pdf_required": false,
  "metadata": { "client_name": "...", "deadline": "..." },
  "departments_needed": ["marketing", "operaciones"],
  "intake_summary": "SALES-FACING ...",
  "ask_whom": [{ "department_id": "marketing", "owner": "Camila Ospina", "ask": "..." }],
  "open_questions": ["..."],
  "requires_ceo_approval": false,
  "work_streams": [
    {
      "department_id": "marketing",
      "owner": "Camila Ospina",
      "label": "Marketing and Digital Experience",
      "key_aspects": ["...", "..."],
      "open_questions": [],
      "next_action": "draft_section",
      "draft_content": null,
      "evaluation_results": null
    }
  ],
  "synthesizer": {
    "departments_for_drafting": ["marketing", "operaciones"],
    "owners": { "marketing": "Camila Ospina" },
    "ask_whom": [],
    "open_questions": [],
    "requires_ceo_approval": false
  },
  "source_pdf_path": "data/raw/rfp/<ticket_id>/file.pdf",
  "markdown_available_in_db": true
}
```

## Part 2 entry (Python)

Canonical path — queue flag + DB field + documented contract:

```python
from data.pipelines.rfp_response import run_response_for_ticket
# Internally: load_ready_part2_handoff(ticket_id)
#   → assert part2_ready + status=intake_complete
#   → validate part2_handoff_json (ticket_id + work_streams[].key_aspects)
#   → generators draft from key_aspects only (never re-ingest PDF)

result = run_response_for_ticket(ticket_id)
```

Queue / contract inspection:

```python
from services.rfp.store import load_part2_handoff, list_part2_queue

for item in list_part2_queue():
    handoff = load_part2_handoff(item["ticket_id"])
    # handoff["ticket_id"] + handoff["work_streams"][i]["key_aspects"]
```

HTTP (same app): `GET /rfp/part2/queue`, `GET /rfp/tickets/{id}/part2-handoff`,
`POST /rfp/tickets/{id}/generate-response`.

Builder: `data.pipelines.rfp_intake.routing.build_part2_handoff` /
`route_intake_to_part2`.
