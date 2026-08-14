# Part 2 readiness — CONTEXT-company.md (read before coding)

Source: CONTEXT-company.md Milestone 9 (§2.1 departments, §2.3 statuses, §5
compliance guidelines, §6 Part 2 deliverable).

## Part 2 scope

- **Build on Part 1** — do not rewrite classifier / routing.
- Start only from tickets Part 1 marked ready via **all** of:
  - queue flag: `part2_ready == true`
  - DB field: `part2_handoff_json`
  - documented contract: `PART2_HANDOFF.md` / `validate_part2_handoff`
- Required payload: `ticket_id` + synthesizer `work_streams[].key_aspects`
  (+ metadata). See `handoff_consume.assert_part1_routing_ready` and
  `run_response_for_ticket` → `load_ready_part2_handoff`.
- **Generators must not re-ingest the raw PDF as primary input**
  (`generate_department_draft` rejects `pdf_path` / `markdown_text` kwargs;
  synthesizer payload strips PDF fields).
- Per active department: a **generator agent** (`marketing_generator_agent`,
  `operaciones_generator_agent`, `procurement_generator_agent`,
  `training_generator_agent`) receives **that department's Part 1 summary**
  (`work_streams[].key_aspects`) and writes that department's section of the
  **pricing proposal** (CONTEXT §2.1 remit). Then evaluators score
  readability, relevance, and compliance (§5).
- Generator–evaluator loop with `MAX_SECTION_ITERATIONS=2` (KPI: avg < 2).
- Persist on `RfpDepartmentSection`: `draft_content`, `evaluation_results_json`.
- Ticket statuses: `drafting` → `under_evaluation` →
  `waiting_for_approval` (all pass) or `needs_human_review` (exhausted).

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
relevance (grounded in Part 1 `key_aspects` + metadata — not the PDF).

## Layout

- Pipeline: `data/pipelines/rfp_response/`
- HTTP: extend `services/rfp/` (same app — no new API process)
