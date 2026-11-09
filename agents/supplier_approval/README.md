# Supplier approval

Collaborative review for a new Brasaland supplier. Procurement (Lucía Fernández) receives the application. Restaurant Operations writes the note management uses before the supplier can feed the 14 kitchens.

## Roles

The handoff is fixed. Each role reads the previous role's output.

| Order | Role | Work |
| --- | --- | --- |
| 1 | Supplier Agent | Parse name, country, categories, emergency surcharge, and status. Colombia → COP. United States → Florida and USD. |
| 2 | Compliance Agent | Ask the existing knowledge base (`data/pipelines/rag.py`, the same path as `POST /knowledge/query`) and apply a rule only when a retrieved chunk states it. |
| 3 | Operations Agent | Write the approval summary for Lucía Fernández. Decision is `approve`, `approve_with_conditions`, or `reject`. |

Orchestration is a plain-Python handoff (`orchestration: plain-python-handoff`). LangGraph and CrewAI are not used: `agent.py` is a manual Groq loop, and those packages are not dependencies. Groq rewrites only the operations narrative when `BRASALAND_SUPPLIER_AGENTS=groq` and `GROQ_API_KEY` is set, through the same OpenAI-compatible client as `agent.py`. The default path does not call Groq.

## How to run

Staff route on the central API (Bearer JWT):

```bash
curl -sS -X POST http://127.0.0.1:8000/suppliers/applications/review \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"raw_text":"Legal name: Carnes Andinas\nCountry: Colombia\nCategories: proteins\nEmergency surcharge: 8%\nINVIMA registration on file."}'
```

From the inventory agent entry point (no API process and no Groq key required):

```bash
python agent.py review-supplier "Legal name: Miami Boxes
Country: United States
Categories: packaging"
```

## Tests

```bash
python -m pytest tests/test_supplier_approval.py -q
```
