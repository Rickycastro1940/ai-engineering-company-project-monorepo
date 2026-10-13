# `infra` folder

This folder contains **infrastructure configurations** for the monorepo (for example: Dockerfiles, Terraform scripts, deployment manifests, Nginx configs, etc.).

- **Main purpose**: to centralize the definition of the infrastructure required to run the company's applications and services.
- **Recommendation**: document how to provision and deploy the infrastructure.

## Nightly export crontab

`cron/brasaland-nightly-export.cron` schedules `scripts/nightly_export.py` outside the FastAPI process.

| Field | Value |
| --- | --- |
| Cron expression | `0 2 * * *` |
| Timezone | `America/Bogota` (`CRON_TZ`) |
| Command | `python scripts/nightly_export.py` |

The installer expects `.venv/bin/python` at the repo root (the same interpreter that can import `services.job_runner`). Install into the user crontab (other lines are kept):

```bash
bash infra/cron/install-nightly-export-cron.sh
```

> _Spanish version: [README.es.md](./README.es.md)._
