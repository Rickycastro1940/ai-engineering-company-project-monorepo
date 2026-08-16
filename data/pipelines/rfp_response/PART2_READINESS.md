# Part 2 readiness — CONTEXT-company.md (read before coding)

Source: CONTEXT-company.md Milestone 9 (§2.1 departments, §2.3 statuses, §5
compliance guidelines, §6 Part 2 deliverable).

## Part 2 scope

- **Build on Part 1** — do not rewrite classifier / routing.
- Start only from tickets Part 1 marked ready via **all** of:
  - queue flag: `part2_ready == true`
  - DB field: `part2_handoff_json`
  - documented contract: `PART2_HANDOFF.md` / `validate_part2_handoff`
  - ticket status in `intake_complete` **or** mid-flight resume
    (`drafting` / `under_evaluation`) so a crash does not strand the ticket
- Required payload: `ticket_id` + synthesizer `work_streams[].key_aspects`
  (+ metadata). See `handoff_consume.assert_part1_routing_ready` and
  `run_response_for_ticket` → `load_ready_part2_handoff`.
- **Generators must not re-ingest the raw PDF as primary input**
  (`generate_department_draft` rejects `pdf_path` / `markdown_text` kwargs;
  synthesizer payload strips PDF fields).
- Per active department: a **generator agent** writes that department's
  proposal section in the **CONTEXT §2.1 format** (required headings taken
  from the contribution column: brand terms / exclusivity / co-branding /
  offer validity; kitchen/staff capacity / setup times / cost per event;
  ingredient cost based on volume / supplier lead times; new recipe or
  standard / development and certification time). Then **three evaluator
  agents run in parallel** over the generated section:
  `readability_evaluator_agent` (`py-readability-metrics`),
  `relevance_evaluator_agent` (§2.1 headings + owner + Part 1 `key_aspects`),
  `compliance_evaluator_agent` (CONTEXT-company.md §5 bullets, not a generic
  SaaS policy checklist). Persist a structured
  `EvaluationResult` on `RfpDepartmentSection.evaluation_results_json`.
- Optional (not graded): generators may ground drafts in the existing
  Brasaland knowledge base (`data.pipelines.rag.retrieve`, same source docs
  as `POST /knowledge/query`) so policy/brand language is real. Disable with
  `RFP_KB_GROUNDING=0`. Failures never block drafting.
- Generator–evaluator loop with `MAX_SECTION_ITERATIONS=2` (KPI: avg < 2).
  Failed sections return to **the same** department generator with
  `EvaluationResult.feedback_for_generator`. Hitting the limit keeps the last
  draft + EvaluationResult, sets **ticket** status to `needs_human_review`,
  keeps section `approval_status=pending` for Part 3 HITL (CONTEXT §2.3 —
  never store ticket status on the section field), and still includes the
  section in the Part 3 handoff (never discarded).
- Ticket statuses (same Part 1 ticket row in PostgreSQL): `intake_complete` →
  `drafting` → `under_evaluation` → `waiting_for_approval` (all pass) or
  `needs_human_review` (exhausted). Drafts and `evaluation_results` persist on
  `RfpDepartmentSection`. No new API process — extend `services/rfp/`.

## §5 guidelines wired into compliance evaluator

Source of truth: `compliance_rules.CONTEXT_SECTION_5_RULES` →
`evaluators.evaluate_compliance` (failures tagged with `rule_id`).

1. `dual_currency` — Prices in both COP and USD labels
2. `brand_pillars` — consistent quality, warm experience, speed of service
3. `min_setup_business_days` — No setup/delivery under 10 business days
4. `no_competitors` — No competitor names
5. `offer_validity` — 30 days from issuance
6. `ceo_threshold` — >$50k flagged for CEO (Part 3; Mariana Restrepo)

Also: readability (sales-facing; TextStat/Flesch when available) and
relevance (CONTEXT §2.1 section headings + owner + Part 1 `key_aspects`
and RFP metadata — not a generic SaaS outline, not the PDF).

## Layout

- Pipeline: `data/pipelines/rfp_response/`
- HTTP: extend `services/rfp/` (same app — no new API process)
