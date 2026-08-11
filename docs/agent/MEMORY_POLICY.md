# Agent memory policy — exact mirror of `CONTEXT-company.md`

**Source of truth:** [`CONTEXT-company.md`](../../CONTEXT-company.md).  
Memorable vs forbidden rules below are taken **only** from that file (not a
generic memory template).

## Strictly forbidden to store

From **RAG constraints** in `CONTEXT-company.md`:

| Forbidden | CONTEXT wording |
| --------- | ---------------- |
| Currency conversion | Keep USD $ and COP $ exactly as written — **never convert** |
| Absolute allergen safety claims | **Never** claim `"zero risk"` or `"100% safe"`; follow source wording |
| Learning the unknown-answer placeholder | Unknown answers → *"There is not enough information available."* (do not persist that as company knowledge) |
| RAG internals | Knowledge/query returns answer string only — **never chunks, scores, or Qdrant payloads** |

Anything else that is not in the memorable list below is **out of scope** for
semantic memory (reject as `not_in_context_company_memorable_domains`).

## Memorable facts (only these domains)

From **Knowledge base source documents** (topics) + **Key people** +
**Audience** (commercial and operations / salesperson perspective):

| Kind | CONTEXT topic / people |
| ---- | ---------------------- |
| `supplier_ordering` | Weekly orders, delivery lead times, minimum protein stock, emergency orders (`brasaland-supplier-ordering.en.md`) |
| `waste` | Waste categories, daily logging, escalation thresholds, operational targets (`brasaland-waste-protocol.en.md`) |
| `loyalty` | Brasa Points tiers, redemption rules, FAQ (`brasaland-loyalty-program.en.md`) |
| `allergen` | Dish allergens, customer allergy protocol, gluten-free limitations (`brasaland-menu-allergens.en.md`) — still never store “zero risk” / “100% safe” |
| `people` | Mariana (CEO); Felipe Guerrero (Operations Director — waste escalation); Lucía Fernández (Procurement Manager — emergency order approval > 500 USD) |

Collection / company slug remain `brasaland_kb` / `brasaland`.

## Not memorable under CONTEXT-company.md

These are **not** listed as memory topics in CONTEXT (keep them in live tools /
traces instead of semantic memory):

- Raw incident-ticket rows from MCP
- Raw inventory product rows from the inventory tool
- Generic secrets/PII rules (not specified in CONTEXT — do not invent extra policy here)

## Implementation

- Enforced in `services/agent/memory/policy.py` (`evaluate_memory_candidate`)
- After each relevant interaction, **self-evaluation** decides new vs corrected
  vs skip — see [`MEMORY_SELF_EVAL.md`](./MEMORY_SELF_EVAL.md)
- Writes only via `MemoryInterface.write` after policy **and** self-eval
- Backend / R/W docs: [`MEMORY_BACKEND.md`](./MEMORY_BACKEND.md),
  [`MEMORY_INTERFACE.md`](./MEMORY_INTERFACE.md)
