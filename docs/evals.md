# Evals and failure testing

## Reproduce

~~~bash
uv sync --extra dev
make verify
docker compose up -d --build
make eval
~~~

The unit/API suite runs against isolated SQLite state. The live demo eval runs through HTTP against the Docker Compose API and PostgreSQL.

## Covered scenarios

| Scenario | Expected invariant |
|---|---|
| Duplicate lead event | One lead |
| Duplicate normalized webhook | Stored response, two original interactions only |
| Duplicate booking retry | One appointment |
| Duplicate discount request | One pending approval |
| DMS outage | State preserved, zero availability claims |
| CRM outage | Lead preserved, failed sync visible |
| NIM timeout | Deterministic response and retryable error code |
| Malformed tool arguments | Tool rejected and traced |
| Nonexistent configuration | No fabricated match |
| Unauthorized discount/booking claim | Generated claim rejected |
| Invented stock or price | Generated claim rejected |
| Service safety complaint | Critical/high urgency |
| Human asks for a person | Human handoff stage |
| Hindi/English input | Bounded business fields extracted |
| Inventory changes before booking | Structured conflict |
| Stale recovery replay | One queue transition |
| DMS restore | Verified search recovers |
| Manager briefing | Stored-state attention items |

## Latest local result

- Automated tests: 27 passed
- Live Docker/PostgreSQL checks: 11/11 passed
- n8n export validation: 8 passed
- n8n 2.38.7 CLI import: 8 passed
- n8n Manager Briefing runtime execution: passed against the live Compose API
- NVIDIA NIM live tool-call preflight: passed with validated arguments on `z-ai/glm-5.3-flash`

These numbers are regression results, not claims about model accuracy in production. There is no statistically meaningful precision/recall score yet because the repository does not ship a labeled real-customer corpus.

## What is not measured

- live conversation quality across a representative multilingual dataset,
- provider latency distribution under load,
- CRM rate-limit recovery over long windows,
- telephony transcription quality,
- sales conversion uplift,
- adversarial coverage beyond the named fixtures.

A production evaluation should add a redacted, consented dataset; tool-choice and grounding labels; policy violation severity; latency/cost; and human reviewer agreement.
