# Part 2 readiness — CONTEXT-company.md (read before coding)

Source: CONTEXT-company.md Milestone 9 (§2.1 departments, §2.3 statuses, §5
compliance guidelines, §6 Part 2 deliverable).

## Part 2 scope

- Start from Part 1 handoff: `ticket_id` + `work_streams[].key_aspects`
  (no PDF reparse; see `data/pipelines/rfp_intake/PART2_HANDOFF.md`).
- Per active department: **generator** writes `draft_content`, then **evaluators**
  score **readability**, **relevance**, and **compliance** (§5).
- Generator–evaluator loop with `MAX_SECTION_ITERATIONS=2` (KPI: avg < 2).
- Persist on `RfpDepartmentSection`: `draft_content`, `evaluation_results_json`.
- Ticket statuses: `drafting` → `under_evaluation` →
  `waiting_for_approval` (all pass) or `needs_human_review` (exhausted).

## §5 guidelines wired into compliance evaluator

1. Prices in both COP and USD labels
2. Brand pillars: consistent quality, warm experience, speed of service
3. No setup/delivery under 10 business days
4. No competitor names
5. Offer validity 30 days from issuance
6. >$50k flagged for CEO (Part 3)

## Layout

- Pipeline: `data/pipelines/rfp_response/`
- HTTP: extend `services/rfp/` (same app — no new API process)
