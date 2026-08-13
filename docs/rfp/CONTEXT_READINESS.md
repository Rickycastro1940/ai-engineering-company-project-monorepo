# RFP Part 1 — CONTEXT readiness (Brasaland)

**Milestone:** Agentic RFP Workflow — Intake & Routing (Part 1 of 3)  
**Rule:** Read [`CONTEXT-company.md`](../../CONTEXT-company.md) before writing implementation code.  
**Fork continuity:** Same monorepo fork; builds on the LangGraph + MCP + memory + harness agent from prior milestones (`feature/agent-guardrails`).

## What CONTEXT-company.md currently defines

| Area | Brasaland facts (source of truth) |
| ---- | --------------------------------- |
| Company | Grilled-food chain — **Colombia** + **Florida (US)** |
| Audience | Commercial and operations teams (salesperson perspective) |
| KB documents | `brasaland-supplier-ordering.en.md`, `brasaland-waste-protocol.en.md`, `brasaland-loyalty-program.en.md`, `brasaland-menu-allergens.en.md` |
| KB topics | Weekly/emergency orders; waste escalation; Brasa Points; menu allergens / gluten-free |
| Collection / slug | `brasaland_kb` / `brasaland` |
| Currency | Keep USD $ and COP $ exactly as written — **never convert** |
| Allergens | Never claim `"zero risk"` or `"100% safe"` |
| Unknown | *"There is not enough information available."* |
| Key people | **Mariana** (CEO); **Felipe Guerrero** (Operations — waste); **Lucía Fernández** (Procurement — emergency orders > 500 USD) |

## What CONTEXT does **not** yet define for this milestone

The Part 1 kickoff says CONTEXT defines **departments**, **RFP format**, **persistence rules**, and company-specific intake guidelines. The current `CONTEXT-company.md` (RAG / support-agent briefing) does **not** yet contain those RFP sections.

Until CONTEXT is extended (or the Part 1 checklist supplies company-exact field names), implementation must **not** invent:

- RFP schema / field names
- Department enum beyond what CONTEXT names
- Persistence backend or retention rules
- Bid / win-loss scoring policies

## CONTEXT anchors usable once Part 1 specs arrive

These are **not** invented departments — they are people/topics already in CONTEXT that intake/routing can bind to when the formal RFP mapping is provided:

| CONTEXT anchor | Role in Brasaland |
| -------------- | ----------------- |
| Lucía Fernández / procurement / supplier ordering / 500 USD | Procurement-facing RFP sections |
| Felipe Guerrero / waste protocol / escalation | Operations-facing RFP sections |
| Mariana / CEO | Executive escalation |
| Menu allergens / gluten-free | Safety / catalog-facing sections |
| Brasa Points / loyalty | Commercial / loyalty-facing sections |
| Live tickets + read-only inventory (existing agent tools) | Operational lookup during intake — not a new RFP invention |

## Prior-sprint capabilities this workflow reuses

- Tools via MCP (`mcps/company_tools`) + read-only inventory
- Memory across interactions (`services/agent/memory`)
- Secure orchestration / harness (`services/agent/harness`)
- Company KB + RAG constraints

## Next

1. Extend or receive CONTEXT RFP sections (departments, format, persistence) **or** the Part 1 implementation checklist.
2. Implement intake + routing under `agents/` / `workflows/` without contradicting CONTEXT restrictions above.
3. Keep currency / allergen / unknown-answer wording CONTEXT-exact.
