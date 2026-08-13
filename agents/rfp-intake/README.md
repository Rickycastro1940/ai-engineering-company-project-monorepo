# RFP Intake agent (Brasaland) — Part 1 scaffold

**Status:** Kickoff only. No intake/routing code until CONTEXT defines RFP format,
departments, and persistence (see [`docs/rfp/CONTEXT_READINESS.md`](../../docs/rfp/CONTEXT_READINESS.md)).

**Depends on:** existing LangGraph support agent + MCP tools + memory + harness
under `services/agent/` and `mcps/company_tools/`.

## Goal (Part 1)

Accept inbound RFP material, structure it per CONTEXT, and route work to the
correct Brasaland owners/topics — without inventing fields or departments
absent from CONTEXT.
