# Brasaland RAG golden set

Question/expected-topic pairs for regression checks against retrieval quality
(`MIN_SCORE` in `data/pipelines/rag.py`, currently `0.68`).

Use after indexing with `uv run python data/process/rag.py`. For each row,
`retrieve(question)` should return at least one chunk whose `source_document`
matches `expected_source` (document label after stripping `brasaland-` /
`.en.md`).

| # | question | expected_source | notes |
|---|----------|-----------------|-------|
| 1 | What is the minimum stock rule for proteins? | supplier-ordering | 3 days of main protein inventory |
| 2 | Who approves emergency orders over 500 USD? | supplier-ordering | Lucía Fernández |
| 3 | What is the delivery lead time for proteins? | supplier-ordering | 48-hour delivery |
| 4 | How often are vegetables and fruit ordered? | supplier-ordering | Monday and Thursday |
| 5 | What waste categories must locations log? | waste-protocol | expiration, kitchen error, unexplained shrinkage |
| 6 | When must waste escalate to Felipe Guerrero? | waste-protocol | premium protein > 5 kg/week or 3 weeks shrinkage |
| 7 | What is the operational waste target? | waste-protocol | below 4% of monthly ingredient cost |
| 8 | How do customers earn Brasa Points? | loyalty-program | 10,000 COP or 10 USD → 1 point |
| 9 | What discount does the Gold tier get? | loyalty-program | 15% permanent + early seasonal menu |
| 10 | Can Brasa Points be used on delivery orders? | loyalty-program | Yes via the app |
| 11 | Does Grilled Sirloin contain soy? | menu-allergens | Marinade contains soy |
| 12 | Are BBQ Ribs gluten-free? | menu-allergens | No certified GF; soy + possible peanut traces |
| 13 | What is the allergy protocol for servers? | menu-allergens | Inform kitchen; never guarantee zero risk |
| 14 | What allergens are in Tropical Salad? | menu-allergens | cashew and feta (dairy) |
| 15 | What is Brasaland's stock ticker symbol? | _(none)_ | Off-topic — expect fallback / no high-score hits |

## How to spot-check

```bash
# Optional: log retrieval hits
export RAG_DEBUG=true

uv run python - <<'PY'
from data.pipelines.rag import retrieve, query

cases = [
    ("What is the minimum stock rule for proteins?", "supplier-ordering"),
    ("Who approves emergency orders over 500 USD?", "supplier-ordering"),
    ("When must waste escalate to Felipe Guerrero?", "waste-protocol"),
    ("How do customers earn Brasa Points?", "loyalty-program"),
    ("Are BBQ Ribs gluten-free?", "menu-allergens"),
    ("What is Brasaland's stock ticker symbol?", None),
]

for question, expected in cases:
    hits = retrieve(question)
    sources = {h.get("source_document") for h in hits}
    ok = (expected is None and not hits) or (expected in sources)
    print(("PASS" if ok else "FAIL"), question, "->", sorted(sources) or "(none)")
    if expected is None:
        print("  answer:", query(question))
PY
```
