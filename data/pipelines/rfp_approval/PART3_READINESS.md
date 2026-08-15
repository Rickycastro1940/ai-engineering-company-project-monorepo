# Part 3 readiness — CONTEXT-company.md (read before coding)

Source: CONTEXT-company.md Milestone 9 (§2.1 owners, §2.3 FinalDocument,
§5 CEO threshold, §6 Part 3 deliverable, §7 conflict triggers).

## Part 3 scope

- **Build on Part 2** — same ticket; last drafts + `EvaluationResult`.
  Do not re-parse the PDF. Do not rewrite classifier / generators.
- **Human-in-the-loop:** each *active* department is signed off by the
  named owner in §2.1 (Camila Ospina, Felipe Guerrero, Lucía Fernández,
  Jake Morrison). No invented VP / Legal / Finance ladder.
- **Extra approver:** Mariana Restrepo (CEO) only when estimated annual
  value exceeds $50,000 USD/year. Block the synthesizer until she
  `approve`s; reject path if she rejects.
- **Arbitration** is a dedicated graph node (`arbitration`) driven by
  detectable contradictions in structured state. Trigger ids:
  `cost-vs-feasibility`, `setup-sla-breach`, `ceo-threshold`. Agents may
  surface a conflict (`conflict_surface_agent`); they must not resolve it
  by free-form consensus.
- **FinalDocument** (CONTEXT §2.3): `ticket_id`, `sections`,
  `total_estimated_value`, `generated_at`. Ticket status becomes `done`
  only after independent owner (and CEO, if required) approval.
- Same HTTP process: extend `services/rfp/` (no second API).
  Pipeline: `data/pipelines/rfp_approval/`.
- **HITL interruption point:** `collect_approvals` is fanned out with
  LangGraph `Send` — one branch per *pending* department. `interrupt()`
  pauses only that branch before the section is marked `approved`.
  Departments already decided are not sent and are not blocked.
  `ceo_gate` interrupts for Mariana Restrepo the same way.

## Durable checkpointer (HITL pause/resume)

LangGraph `interrupt()` needs a checkpointer. Do **not** use
`MemorySaver` or SQLite `:memory:` outside local development.

| Environment | Backend |
| ----------- | ------- |
| `DATABASE_URL` PostgreSQL (Supabase / production) | `PostgresSaver` (`langgraph-checkpoint-postgres`) |
| Local smoke / pytest (`RFP_ALLOW_SQLITE=1` or sqlite URL) | file-backed `SqliteSaver` (`langgraph-checkpoint-sqlite`) |
| Local only, explicit `RFP_CHECKPOINT_MEMORY=1` | `MemorySaver` |

Install extras with `uv add langgraph-checkpoint-sqlite langgraph-checkpoint-postgres 'psycopg[binary,pool]'`.
Override the SQLite file with `RFP_CHECKPOINT_SQLITE=/path/to/file.sqlite`.
