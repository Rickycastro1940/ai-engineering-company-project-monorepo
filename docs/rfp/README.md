# Brasaland — Agentic RFP Workflow

| Part | Focus | Status |
| ---- | ----- | ------ |
| **1 of 3** | Intake & Routing | In progress — backoffice upload + markitdown / readability |
| 2 of 3 | (later) | — |
| 3 of 3 | (later) | — |

**Upload UI:** [`uis/backoffice/rfp-upload.html`](../../uis/backoffice/rfp-upload.html) (extends existing backoffice).  
**API:** `POST /rfp/upload` in [`services/rfp`](../../services/rfp/__init__.py).  
**Deps:** `markitdown`, `py-readability-metrics` (via `uv add` only).
