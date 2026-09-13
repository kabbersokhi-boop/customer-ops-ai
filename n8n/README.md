# n8n workflows

These exports make orchestration visible without hiding policy inside Code or Function nodes.

| Export | Business purpose |
|---|---|
| inbound-lead.json | Customer Enquiry Intake: normalize channel payload, invoke the control layer, and prioritize service/safety work |
| appointment-confirmation.json | Service Booking & Confirmation: distinguish confirmed, replayed, and recovery states |
| service-case-routing.json | Service Escalation & Routing: create a service case and route safety escalation |
| approval-decision.json | Apply a typed manager decision and expose the delivery boundary |
| lost-lead-recovery.json | Find stale high-intent leads and queue recovery |
| provider-error-handler.json | Integration Failure Recovery: classify errors and preserve safe retry rules |
| manager-briefing.json | Manager Operations Briefing: pull grounded metrics and prepare delivery |
| system-health-alert.json | Operations Health Monitor: detect safe fallback and prepare an alert |

## Connectivity

Attach n8n to the Compose network, then use the service name:

~~~bash
docker network connect customer-ops-ai_default n8n
~~~

Create the n8n Variable `CUSTOMER_OPS_API_BASE_URL` with value `http://api:8000`, or rely on the same built-in Docker-network fallback. The exports use `$vars` because expression access to `$env` is blocked by default in current n8n releases.

If ADMIN_API_KEY is enabled in the API, add an HTTP Header Auth credential in n8n and select it only on manager/admin HTTP Request nodes. Never export the credential.

## Import

Use Workflows → Import from File, or the CLI:

~~~bash
n8n import:workflow --input=/path/to/workflow.json
~~~

All eight files retain stable workflow IDs. Only Customer Enquiry Intake and Service Booking & Confirmation should be published for the browser demo; provider-bound schedules and callbacks remain inactive until a real destination is configured.

For the browser demo, publish only the inbound and appointment workflows after inspection:

~~~bash
n8n publish:workflow --id=coa-inbound-channel
n8n publish:workflow --id=coa-appointment-confirm
~~~

Restart a running n8n process after CLI import/publish so production webhooks are registered. Confirm both webhook URLs return a successful CORS preflight before enabling n8n mode.

## Browser-first demo mode

Configure the application, not the exported workflows:

~~~dotenv
ORCHESTRATION_MODE=n8n
N8N_INBOUND_WEBHOOK_URL=http://localhost:5678/webhook/customer-ops/inbound
N8N_APPOINTMENT_WEBHOOK_URL=http://localhost:5678/webhook/customer-ops/appointments
N8N_UI_BASE_URL=http://localhost:5678
~~~

Both `/customer` and the manager dashboard discover this public routing configuration from `/api/demo/config`. A customer message visibly follows Browser → n8n → FastAPI → NVIDIA NIM/PostgreSQL/Airtable → n8n → Browser. The normalized event preserves typed conversation continuity, and the response includes n8n workflow and execution IDs. NVIDIA NIM and all policy remain behind FastAPI.

Webhook URLs must not contain credentials, query tokens, fragments, or URL user-info; unsafe values are rejected and that command route falls back to FastAPI. Use `ORCHESTRATION_MODE=direct` for tests and offline local work.

## Manual steps

1. Configure the n8n Variable `CUSTOMER_OPS_API_BASE_URL`. The exports fall back to `http://api:8000` for the documented Docker network and do not require expression-level environment access.
2. Select the optional admin-header credential if admin protection is enabled.
3. Replace provider-boundary Set nodes with approved Slack, email, WhatsApp Business, or service-desk credentials.
4. Test each workflow manually before publishing it.
5. Attach Integration Failure Recovery as the error workflow for production-bound workflows.
