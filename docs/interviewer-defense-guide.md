# Interviewer defense guide

Use this to understand and defend the project rather than memorizing lines.

## "Is the WhatsApp integration real?"

The public demo uses a simulated messaging transport. The normalized event contract and downstream workflow are real. A Meta WhatsApp Cloud API adapter would translate provider webhooks into the same event shape and send replies through the provider without changing lead/inventory/approval logic.

Do not imply a personal WhatsApp account is a production WhatsApp Business integration.

## "Is this real Toyota inventory?"

No. Inventory, prices, customers and operating history are synthetic demo data. The important design point is that inventory is behind an explicit DMS/data boundary, so a real DMS adapter can replace the synthetic implementation.

## "Why PostgreSQL if Airtable is already a database?"

Airtable is standing in for CRM. Inventory/DMS state, idempotency keys, appointments, audit events and execution/reliability state should not be coupled to a CRM SaaS product. PostgreSQL represents durable operational truth in the reference architecture.

## "What does the LLM actually do?"

It helps interpret and formulate customer interactions, and can invoke bounded read-only tools. Deterministic code owns policy, database mutation, idempotency, approvals and failure behavior. The system still works in deterministic fallback mode if the LLM is unavailable.

## "Why not put the whole agent in n8n?"

n8n is excellent for integration and workflow visibility. Business rules, typed domain logic, tests, idempotency and provider-neutral APIs are easier to maintain and validate in the application layer. Keeping those boundaries clear also makes workflows less brittle.

## "What would you change for production?"

Authentication/RBAC, secrets manager, Alembic migrations, queue-backed retries, observability/tracing, provider-specific circuit breakers, PII controls, formal evals, live CRM/DMS adapters, production WhatsApp/telephony, deployment hardening and load/security testing.

## "Did AI help you build it?"

Answer truthfully. A strong formulation if accurate is:

> I used AI as a development accelerator, the same way I would use it on the job. I own the architecture, business boundaries, testing decisions and integration design, and I can walk through or modify any part of the system.

The project should withstand technical questioning because you understand it, not because the provenance is hidden.
