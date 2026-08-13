# Brasaland backoffice (internal admin UI)

Static HTML served by the reporting API (`services/reporting/main.py`).

| Page | Path | Purpose |
| ---- | ---- | ------- |
| Leadership KPIs | [`index.html`](./index.html) | Weekly location performance |
| Telemetry | [`telemetry.html`](./telemetry.html) | Engineering health report |
| **RFP Intake** | [`rfp-upload.html`](./rfp-upload.html) | Upload RFP docs for Part 1 intake & routing |

## RFP upload

- UI: `rfp-upload.html` (extend this app — do **not** create a separate frontend)
- API: `POST /rfp/upload` (`services/rfp`) — converts with **markitdown**, scores with **py-readability-metrics**
- Storage: `data/process/rfp-intake/<id>/`

```bash
# from repo root, with reporting API running and mounting uis/backoffice
open http://127.0.0.1:8000/rfp-upload.html
```
