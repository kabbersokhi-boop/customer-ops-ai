# Archived pre-pivot demo evidence

These files preserve a sanitized, browser-content-only replay from the earlier sales-oriented interface. They prove the integration path existed at the recorded commit, but they are **not current screenshots of the service-operations experience** and should not be used in the interview deck. Capture the replacement set in `docs/demo-script.md` after the final hands-on run.

## Provenance

- Application commit under test: `b0353ff1123bee97c5c19faa25ab6dc84cd0292b`
- Capture date: 2026-09-13 (Asia/Kolkata)
- Customer transport: simulated browser messaging, not WhatsApp
- Business data: synthetic automotive inventory, identities, pricing, and operational history
- NVIDIA NIM: live; model `z-ai/glm-5.3-flash`; guarded inventory tool call completed
- PostgreSQL: live local Docker service; operational source of truth
- Airtable: live; five-table schema compatible; lead journey reported `SYNCED`
- n8n: live self-hosted version 2.38.7; published inbound and appointment webhooks

The captured customer journey produced these n8n execution-store records:

| Execution | Workflow | Result | Meaning |
|---:|---|---|---|
| 76 | `coa-inbound-channel` | success | Browser enquiry returned through n8n after governed NIM, PostgreSQL, and Airtable work |
| 77 | `coa-appointment-confirm` | success | First typed appointment command created one booking |
| 78 | `coa-appointment-confirm` | success | Identical command replay returned the existing booking |

Execution timestamps and durations in `n8n-execution.png` were read from n8n's local execution database. The image is an explicitly labelled sanitized canvas, not a screenshot of a logged-in personal n8n account. Customer payloads, execution data blobs, credentials, and cookies were deliberately omitted.

## Files

- `customer-experience.png` — the distinct customer UI showing n8n execution 76, live guarded NIM, verified synthetic inventory, and Airtable sync
- `operations-console.png` — the superseded engineering-oriented operations console
- `n8n-execution.png` — sanitized workflow and execution-store evidence for executions 76–78
- `customer-flow.gif` — lightweight animated replay assembled only from the sanitized browser-content frames above and booking/replay frames

## Verification performed

~~~bash
make verify
# Ruff: passed
# n8n exports: 8 validated
# secret/history scan: passed
# pytest: 42 passed at the archived commit

make demo-ready
# FastAPI/PostgreSQL/pages/seed/n8n webhooks: passed
# NIM live tool calling: passed
# Airtable base access and five-table schema: passed

make eval
# 11/11 live Docker/PostgreSQL policy and failure checks passed

make orchestration-eval
# n8n inbound create/replay and appointment create/replay passed
# one durable booking

make adversarial-eval
# 16/16 customer inputs passed through the configured n8n route
~~~

These archived screenshots and every GIF source frame were visually inspected before commit. They contain no desktop, panel,
system tray, personal browser profile, bookmarks, notifications, account avatar, API key, Airtable PAT, NVIDIA key,
n8n credential, cookie, email, terminal, local path, or real customer information. Any visible name, phone-like value,
vehicle, stock ID, price, or operational count comes from the deterministic synthetic seed.

## Integrity

~~~text
c218d2ffc6a2b738243517b74a4ddd2116eaece9111d6a4f9bc815ad869bcf70  customer-experience.png
a0b1e16feebafdce629f820880d20b010e812a63748865887af647118f96bff1  operations-console.png
773d3d5baee5a87033375e6d773d90977e6a3409dc81251d1ca431bed681e91f  n8n-execution.png
9a75acf82145645cfd159720f95f1f308333e5d39787673784587cf4ea64c993  customer-flow.gif
~~~

These hashes verify the committed media bytes, not the availability of external providers at a later date.
