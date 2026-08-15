# Part 3 completion — FinalDocument

Once **every active department** has logged approval (and Mariana Restrepo
when estimated annual value exceeds USD $50,000/year), the graph reaches
the ultimate synthesizer and generates the CONTEXT §2.3 **FinalDocument**
by consolidating the approved section drafts.

## When completion runs

```
… → join_approvals → ceo_gate → synthesizer → END
```

`synthesizer_ready` gates generation:

| Condition | Result |
| --------- | ------ |
| Any active department still `pending` / `rejected` / `request_changes` | Blocked — no FinalDocument |
| CEO required and Mariana not yet `approved` | Blocked |
| Every required owner (and CEO if needed) `approved` | Consolidate → persist → ticket `done` |

Rejected or change-requested drafts are **not** included in the body.
Only sections whose status is `approved` are consolidated.

## FinalDocument fields (CONTEXT §2.3)

| Field | Source |
| ----- | ------ |
| `ticket_id` | Same Part 1 ticket |
| `sections` | Approved department drafts + labels / owners |
| `total_estimated_value` | Intake metadata (`estimated_contract_value_usd`) — never invented |
| `generated_at` | UTC timestamp at synthesis |

Markdown is also stored for the backoffice (`GET /rfp/tickets/{id}/final-document`).

## Code

| Piece | Location |
| ----- | -------- |
| Gate + consolidate | `data/pipelines/rfp_approval/synthesizer.py` |
| Graph node | `synthesizer_node` in `graph.py` |
| Persist | `persist_part3_progress` → `RfpFinalDocument` |
| HTTP | `GET /rfp/tickets/{ticket_id}/final-document` |

Helpers: `synthesizer_ready`, `consolidate_approved_sections`, `build_final_document`.
