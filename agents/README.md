# `agents` folder

This folder contains the monorepo’s **AI agents** (assistants, internal copilots, support/operations agents, etc.) built as part of the cross-functional AI Engineering milestones.

Each subfolder under `agents/` should represent **one concrete agent** (for example `support-agent`, `onboarding-agent`, `sales-assistant`) with its own documentation: goal, capabilities, knowledge/memory sources, available tools, and how to test it.

- **Main purpose**: centralize reusable agent development for the company in one monorepo.
- **Recommendation**: maintain a catalog of agents here as they are created and link to each agent’s README.

> _Spanish version: [README.es.md](./README.es.md)._

## Catalog

| Agent | Location | Status |
|-------|----------|--------|
| Brasaland support agent (LangGraph Part 1) | [`services/agent/`](../services/agent/) | Migration + explicit RAG flow with traces |
| Brasaland RFP intake (Part 1) | [`rfp-intake/`](./rfp-intake/) | Backoffice upload + markitdown / readability |
