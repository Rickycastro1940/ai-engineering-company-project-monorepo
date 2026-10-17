# `packages` folder

This folder contains **shared packages** for the monorepo: internal libraries, utilities, types, shared components, SDKs, clients, and any code reused by multiple applications, agents, or pipelines.

`packages/shared/incident_rules.py` is the shared Brasaland incident validator (analyzer CSV rules plus the live manager enums, branch labels, and status transitions). `scripts/seed_incidents.py` and `services/api/incidents.py` both import it.

Each subfolder under `packages/` should represent **one versionable package** (for example `shared-types`, `ui`, `analytics-sdk`) with its own README.

- **Main purpose**: encourage reuse and consistency across all company deliverables.
- **Recommendation**: document packages as you add them—their public API and how they are consumed from `apps/`, `agents/`, and `workflows/`.

> _Spanish version: [README.es.md](./README.es.md)._
