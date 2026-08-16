# Part 3 completion — FinalDocument

Once **every active department** has logged approval (and Mariana Restrepo
when estimated annual value exceeds USD $50,000/year), the graph reaches
the ultimate synthesizer and generates the CONTEXT §2.3 **FinalDocument**
by consolidating the approved section drafts.

## Ticket status (completion rules)

| Condition | Ticket status | FinalDocument |
| --------- | ------------- | ------------- |
| Any active department approval still open | `waiting_for_approval` | Not available (`GET .../final-document` → 409) |
| CEO required and Mariana not yet approved | `waiting_for_approval` | Not available |
| FinalDocument stored after all required approvals | `done` | Accessible via `GET /rfp/tickets/{id}/final-document` and on `GET /rfp/tickets/{id}` |

Persisting a FinalDocument through `persist_part3_progress` always sets the
ticket to `done` — a stored document is never left on a still-waiting ticket.

## When completion runs

```
… → join_approvals → ceo_gate → synthesizer → END
```

`synthesizer_ready` gates generation:

| Condition | Result |
| --------- | ------ |
| Any active department still `pending` / `rejected` / `request_changes` | Blocked — status stays `waiting_for_approval`, no FinalDocument |
| CEO required and Mariana not yet `approved` | Blocked — status stays `waiting_for_approval` |
| Every required owner (and CEO if needed) `approved` | Consolidate → store FinalDocument → status `done` |

Rejected or change-requested drafts are **not** included in the body.
Only sections whose status is `approved` are consolidated.

## FinalDocument fields (CONTEXT §2.3)

| Field | Source |
| ----- | ------ |
| `ticket_id` | Same Part 1 ticket |
| `sections` | Approved department drafts + labels / owners (§2.1 named owners only) |
| `total_estimated_value` | Intake metadata (`estimated_contract_value_usd`) — never invented |
| `generated_at` | UTC timestamp at synthesis |

These four fields are required (`CONTEXT_FINAL_DOCUMENT_FIELDS` /
`assert_final_document_context_shape`). Markdown and other helpers are extras
for UI — they do not replace the CONTEXT schema.

**Sign-off + arbitration (not generic):** department approvers are exactly
Camila Ospina / Felipe Guerrero / Lucía Fernández / Jake Morrison; CEO extra
approver is only Mariana Restrepo when value > $50k USD/year. §7 trigger ids
are `cost-vs-feasibility`, `setup-sla-breach`, `ceo-threshold` with those
fixed arbiters — see `context_rules.CONTEXT_ARBITRATION_RULES`.

## Code

| Piece | Location |
| ----- | -------- |
| Gate + consolidate | `data/pipelines/rfp_approval/synthesizer.py` |
| Graph node | `synthesizer_node` in `graph.py` |
| Persist (`waiting_for_approval` / `done`) | `persist_part3_progress` → `RfpFinalDocument` |
| HTTP (accessible only when `done`) | `GET /rfp/tickets/{ticket_id}/final-document` |

Helpers: `synthesizer_ready`, `consolidate_approved_sections`, `build_final_document`.

## End-to-end review

Run at least one CONTEXT seed through all four parts on the **same ticket**:

```bash
RFP_INTAKE_SYNC=1 RFP_ALLOW_SQLITE=1 \
  uv run pytest tests/pipelines/test_rfp_e2e_full_pipeline.py -q
```

| Seed | Path |
| ---- | ---- |
| Andes Tech (informal, no CEO) | intake → generate → start-approval → named-owner approvals → `done` + FinalDocument |
| Sunset Bay (formal, CEO) | same, plus Mariana Restrepo before `done` |

The Andes journey asserts one `ticket_id`, status transitions
(`intake_complete` → … → `waiting_for_approval` → `done`), stable
`departments_needed` / client metadata, and FinalDocument accessibility only
after completion.

## Reproducible Part 3 path (simulated approvals — no UI)

Reviewers must not depend on irreproducible UI clicks alone. Ship path:

| Piece | Location |
| ----- | -------- |
| Fixture (sections + simulated owner decisions) | `data/pipelines/rfp_approval/fixtures.py` |
| Script (queued or sequential programmatic resume) | `scripts/rfp_part3_e2e_simulated_approvals.py` |
| Integration tests | `tests/pipelines/test_rfp_part3_simulated_approvals_e2e.py` |

```bash
RFP_ALLOW_SQLITE=1 \
  uv run python scripts/rfp_part3_e2e_simulated_approvals.py --mode sequential

RFP_ALLOW_SQLITE=1 \
  uv run python scripts/rfp_part3_e2e_simulated_approvals.py --scenario sunset --mode queued

RFP_ALLOW_SQLITE=1 \
  uv run pytest tests/pipelines/test_rfp_part3_simulated_approvals_e2e.py \
    tests/pipelines/test_rfp_part3_interrupt_arbitration_e2e.py -q
```

Approvals are CONTEXT named owners via `queued_decisions` / `resume=`
(LangGraph `Command(resume=)` equivalent), not browser clicks.

HITL coverage also includes: successful interrupt/resume, iteration-limit →
`needs_human_review`, §7 arbitration on disagreement, and approve department B
while A remains interrupted (parallel Send branches) — see
`tests/pipelines/test_rfp_part3_interrupt_arbitration_e2e.py`.
