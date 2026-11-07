# `agents` folder

This folder contains the monorepo’s **AI agents** (assistants, internal copilots, support/operations agents, etc.) built as part of the cross-functional AI Engineering milestones.

Each subfolder under `agents/` should represent **one concrete agent** (for example `support-agent`, `onboarding-agent`, `sales-assistant`) with its own documentation: goal, capabilities, knowledge/memory sources, available tools, and how to test it.

- **Main purpose**: centralize reusable agent development for the company in one monorepo.
- **Recommendation**: maintain a catalog of agents here as they are created and link to each agent’s README.

## Catalog

- [supplier_approval](./supplier_approval/README.md) — Supplier, Compliance, and Operations review an incoming supplier application and write an approval summary for Procurement. Compliance uses the existing knowledge base. Entry points: `POST /suppliers/applications/review` and `python agent.py review-supplier`.

> _Spanish version: [README.es.md](./README.es.md)._
