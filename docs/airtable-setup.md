# Airtable CRM setup

Airtable is a reference CRM adapter, not inventory or operational truth. PostgreSQL retains lead-event idempotency, bookings, approvals, audit events, service cases, and synthetic DMS inventory if Airtable is unavailable.

## PAT permissions

Create a personal access token restricted to the demo base with:

- records:read
- records:write
- schema.bases:read if you use Airtable metadata tooling

Do not place the token in this repository or an n8n export.

## Tables and fields

Field names are configurable at the table level through environment variables. The adapter uses the identifier fields below for lookup-then-create/update upserts.

### Customers

| Field | Suggested type |
|---|---|
| Customer ID | Single line text, unique business key |
| Name | Single line text |
| Phone | Phone or single line text |
| Email | Email |
| Created At | Date/time |

### Leads

| Field | Suggested type |
|---|---|
| Lead ID | Single line text, unique business key |
| Customer ID | Single line text |
| Channel | Single select or text |
| Intent | Single select or text |
| Model Interest | Single line text |
| Budget INR | Currency or number |
| Colour | Single line text |
| Transmission | Single line text |
| Timeline Days | Number |
| Trade In | Single line text |
| Lead Score | Number |
| Stage | Single select or text |
| Summary | Long text |

### Activities

| Field | Suggested type |
|---|---|
| Activity ID | Single line text, unique business key |
| Lead ID | Single line text |
| Direction | Single select or text |
| Channel | Single select or text |
| Intent | Single select or text |
| Content | Long text |
| Created At | Date/time |

### Appointments

| Field | Suggested type |
|---|---|
| Appointment ID | Single line text, unique business key |
| Lead ID | Single line text |
| Kind | Single select or text |
| Branch | Single select or text |
| Stock ID | Single line text |
| Scheduled For | Date/time |
| Status | Single select or text |
| Idempotency Key | Single line text |

### Approval Requests

| Field | Suggested type |
|---|---|
| Approval ID | Single line text, unique business key |
| Lead ID | Single line text |
| Action | Single select or text |
| Requested Value | Single line text |
| Recommendation | Long text |
| Status | Single select or text |
| Decision Value | Single line text |
| Created At | Date/time |

## Environment

~~~bash
AIRTABLE_API_KEY=your-local-secret
AIRTABLE_BASE_ID=your-base-id
AIRTABLE_BASE_WEB_URL=https://airtable.com/your-base-or-interface
AIRTABLE_ENABLED=true
~~~

Optional table mappings:

~~~bash
AIRTABLE_CUSTOMERS_TABLE=Customers
AIRTABLE_LEADS_TABLE=Leads
AIRTABLE_ACTIVITIES_TABLE=Activities
AIRTABLE_APPOINTMENTS_TABLE=Appointments
AIRTABLE_APPROVALS_TABLE=Approval Requests
~~~

## Sync behavior

Each entity is looked up by its deterministic business ID. Existing rows are patched; missing rows are created. Timeouts, network errors, rate limits, and server errors use a bounded retry policy. The application stores sync status, attempt count, provider record ID, base link, operation, and a non-sensitive error code.

CRM failure never rolls back already committed domain state. Failed rows remain visible on the manager dashboard for controlled replay.

Verify PAT access and the configured table/field contract without printing credentials or records:

~~~bash
make providers
# or: .venv/bin/python scripts/verify_live_providers.py airtable
~~~

For a new or incomplete base, preview the additive schema plan first. Applying it requires the PAT scope `schema.bases:write`; the script never deletes tables, fields, or records.

~~~bash
.venv/bin/python scripts/bootstrap_airtable.py
.venv/bin/python scripts/bootstrap_airtable.py --apply
.venv/bin/python scripts/verify_live_providers.py airtable
~~~
