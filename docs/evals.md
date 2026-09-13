# Evals and failure testing

## Reproduce

~~~bash
uv sync --extra dev
make verify
docker compose up -d --build
make eval
make orchestration-eval  # run with published n8n webhooks and ORCHESTRATION_MODE=n8n
make adversarial-eval
~~~

The unit/API suite runs against isolated SQLite state. The live demo eval runs through HTTP against the Docker Compose API and PostgreSQL. The orchestration eval discovers the same runtime route as the browser, executes inbound and appointment replays through n8n, and verifies one durable booking.

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
| Greeting or gibberish | Clarification without unnecessary model use |
| Budget-only enquiry | Bounded inventory search without a named model |
| Unsupported vehicle | Explicit catalogue boundary |
| Warranty/specification/finance question | No answer from unapproved model memory |
| Multi-turn conversation | Same customer lead enriched safely |
| Natural-language discount injection | Pending typed approval; no model authority |
| Free-text booking request | Cannot bypass typed appointment command |

## Latest local result

- Automated tests: 42 passed
- Live Docker/PostgreSQL checks: 11/11 passed
- n8n export validation: 8 passed
- n8n 2.38.7 CLI import: 8 passed
- n8n Manager Operations Briefing runtime execution: passed against the live Compose API
- n8n-first runtime eval: inbound and appointment webhooks passed with visible execution IDs; duplicate booking count was one
- NVIDIA NIM live tool-call preflight: passed with validated arguments on `z-ai/glm-5.3-flash`
- Airtable live replay proof: one Lead row, two Activity rows, and one Appointment row after duplicate commands
- Live customer adversarial suite: 16/16 expected outcomes through the configured route

These numbers are regression results, not claims about model accuracy in production. There is no statistically meaningful precision/recall score yet because the repository does not ship a labeled real-customer corpus.

The release suite also covers greeting/clarification, budget-only discovery, unsupported vehicles, warranty/specification/finance scope boundaries, multi-turn lead continuity, natural-language discount approval, free-text booking authority, gibberish, and the distinct customer page.

## What is not measured

- live conversation quality across a representative multilingual dataset,
- provider latency distribution under load,
- CRM rate-limit recovery over long windows,
- telephony transcription quality,
- sales conversion uplift,
- adversarial coverage beyond the named fixtures.

A production evaluation should add a redacted, consented dataset; tool-choice and grounding labels; policy violation severity; latency/cost; and human reviewer agreement.
