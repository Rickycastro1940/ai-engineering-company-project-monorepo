# Brasaland backoffice (internal admin UI)

Static HTML served by `services.agent.app` (and reporting).

| Page | Path | Purpose |
| ---- | ---- | ------- |
| Leadership KPIs | `index.html` | Weekly location performance |
| Telemetry | `telemetry.html` | Engineering health report |
| **RFP Intake** | `rfp-upload.html` | Upload curriculum PDFs → ticket intake |

Upload posts to `POST /rfp/tickets` and polls `GET /rfp/tickets/{id}`.
Sample files: `rfp-requests/brasaland/*.pdf`.
