# Architecture decisions

## ADR-001 — FastAPI owns business controls

**Decision:** Keep validation, idempotency, inventory boundaries, commercial policy, and audit emission in typed Python services.

**Why:** These rules need version control, tests, review, and provider neutrality. n8n still exposes orchestration clearly.

## ADR-002 — PostgreSQL is operational truth

**Decision:** Use PostgreSQL for synthetic DMS data and durable operational state; treat Airtable as a CRM projection.

**Why:** CRM availability and schema changes must not define booking, audit, or inventory correctness.

## ADR-003 — Read-only model tool

**Decision:** Allow NVIDIA NIM to request verified inventory search but expose no mutation tool.

**Why:** Tool use improves grounded responses without making prompt behavior an authorization mechanism.

## ADR-004 — Deterministic fallback

**Decision:** Preserve a complete non-LLM response path.

**Why:** A customer request should remain safe and useful during model timeouts, credential problems, or malformed output.

## ADR-005 — Explicit idempotency

**Decision:** Store normalized channel receipts and appointment command keys.

**Why:** Webhook and workflow retries are expected distributed-systems behavior.

## ADR-006 — No LangGraph

**Decision:** Do not add a graph framework to the current request path.

**Why:** The present state machine is short, deterministic, and visible in ordinary services. A graph framework becomes useful only when multi-step recovery, resumable checkpoints, or several autonomous tool loops justify it.

## ADR-007 — Zero-build operations console

**Decision:** Keep one server-hosted HTML application.

**Why:** It reduces demo setup and supply-chain surface while still exposing operational state. A production console would use authenticated routes and a maintained frontend stack.
