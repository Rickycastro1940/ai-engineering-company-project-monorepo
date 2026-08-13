# RFP Intake (Brasaland) — Part 1

Pipeline: [`data/pipelines/rfp_intake/`](../../data/pipelines/rfp_intake/).  
HTTP: [`services/rfp/`](../../services/rfp/) on `services.agent.app` (same process).  
UI: [`uis/backoffice/rfp-upload.html`](../../uis/backoffice/rfp-upload.html).  
Seeds: [`rfp-requests/brasaland/`](../../rfp-requests/brasaland/).

```bash
uv run python scripts/rfp_intake_smoke.py
uv run uvicorn services.agent.app:app --reload --port 8000
```
