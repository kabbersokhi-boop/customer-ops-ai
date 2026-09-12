# Threat model

## Assets

- customer contact details and message content,
- booking and approval state,
- inventory and pricing claims,
- provider credentials,
- audit integrity,
- manager-only controls.

## Trust boundaries

1. public or provider-controlled channel payloads,
2. n8n workflow execution,
3. FastAPI control layer,
4. NVIDIA NIM,
5. Airtable,
6. PostgreSQL,
7. manager console.

## Primary threats and controls

| Threat | Implemented control | Remaining work |
|---|---|---|
| Prompt injection | Customer text labelled untrusted; no mutation tools; output guard | Broader adversarial corpus |
| Fabricated stock/price | Database tool boundary and grounding checks | Structured claim verifier |
| Unauthorized discount | Deterministic threshold and human approval | Identity-backed approval roles |
| Duplicate webhook/booking | Unique receipts and idempotency keys | Cross-region strategy |
| Provider credential leak | Environment-only config, ignored .env, source/history scan | Managed secret vault |
| CRM outage | Domain commit first, bounded retry, sync ledger | Queue-backed outbox |
| DMS outage | Explicit unavailable state and safe response | Real adapter circuit breaker |
| PII in logs | Request bodies are not logged by application code | Formal redaction and retention |
| Admin endpoint abuse | Optional admin header | OAuth/OIDC, RBAC, CSRF controls |
| Workflow replay | Idempotent API boundaries | Signed provider webhooks |

## Security posture

The local console is intentionally unauthenticated when ADMIN_API_KEY is blank. Do not expose this mode to the public internet. Production deployment needs identity, authorization, transport security, rate limiting, webhook signature verification, centralized audit export, encrypted secrets, and a retention policy.
