# Brasaland backoffice (internal admin UI)

Static HTML served by `services.agent.app` (and reporting).

| Page | Path | Purpose |
| ---- | ---- | ------- |
| Leadership KPIs | `index.html` | Weekly location performance |
| Telemetry | `telemetry.html` | Engineering health report |
| **RFP Intake** | `rfp-upload.html` | Upload curriculum PDFs → ticket intake; each department logs approve / reject |
| **RFP Approvals** | `rfp-approvals.html` | Part 3 queue helper for the same named-owner sign-off |

Upload posts to `POST /rfp/tickets` and polls `GET /rfp/tickets/{id}`.
Department owners sign off with `POST /rfp/tickets/{id}/start-approval` and
`POST /rfp/tickets/{id}/approvals`. After every required owner (and CEO if
needed) approves, the ticket becomes `done` and
`GET /rfp/tickets/{id}/final-document` returns the consolidated FinalDocument.
Sample files: `rfp-requests/brasaland/*.pdf`.
