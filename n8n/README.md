# n8n workflows

These exports make orchestration visible without hiding policy inside Code or Function nodes.

| Export | Business purpose |
|---|---|
| inbound-lead.json | Normalize channel payload, invoke the control layer, route high intent |
| appointment-confirmation.json | Create an idempotent booking and suppress duplicate notifications |
| service-case-routing.json | Create a service case and route safety escalation |
| approval-decision.json | Apply a typed manager decision and expose the delivery boundary |
| lost-lead-recovery.json | Find stale high-intent leads and queue recovery |
| provider-error-handler.json | Classify workflow errors and preserve safe retry rules |
| manager-briefing.json | Pull a stored-state briefing and prepare manager delivery |
| system-health-alert.json | Detect safe-fallback state and prepare an operations alert |

## Connectivity

Attach n8n to the Compose network, then use the service name:

~~~bash
docker network connect customer-ops-ai_default n8n
CUSTOMER_OPS_API_BASE_URL=http://api:8000
~~~

The exports default to http://api:8000 when the variable is absent.

If ADMIN_API_KEY is enabled in the API, add an HTTP Header Auth credential in n8n and select it only on manager/admin HTTP Request nodes. Never export the credential.

## Import

Use Workflows → Import from File, or the CLI:

~~~bash
n8n import:workflow --input=/path/to/workflow.json
~~~

All eight files have stable workflow IDs and were imported successfully using n8n 2.38.7. They remain inactive after import so provider boundaries cannot send unintended messages.

## Manual steps

1. Configure CUSTOMER_OPS_API_BASE_URL.
2. Select the optional admin-header credential if admin protection is enabled.
3. Replace provider-boundary Set nodes with approved Slack, email, WhatsApp Business, or service-desk credentials.
4. Test each workflow manually before activation.
5. Attach Provider Error Handler as the error workflow for the other workflows.
