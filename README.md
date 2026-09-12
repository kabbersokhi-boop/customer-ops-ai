# AI Customer Operations Control Layer

An interview-grade reference system for connecting LLM reasoning to customer operations without giving the model authority over inventory, bookings, discounts, or database writes.

The reference tenant uses **synthetic Toyota India-style automotive data**. It is not affiliated with Toyota and does not contain live inventory, pricing, customers, WhatsApp traffic, or telephony.

## The business problem

Sales and service teams lose revenue when customer context is fragmented across channels, follow-up is late, provider failures create duplicate actions, and assistants make claims that are not grounded in operational systems.

This project turns one inbound message into visible, governed business state:

~~~mermaid
flowchart LR
    C[Demo messaging / browser voice] --> N[n8n orchestration]
    N --> A[FastAPI control layer]
    A --> E[Lead + service extraction]
    A --> T[Bounded NIM tool use]
    T --> D[(PostgreSQL synthetic DMS)]
    A --> R[Airtable CRM upserts]
    A --> P[Typed bookings + approvals]
    P --> U[Operations console + audit]
    D --> U
    R --> U
~~~

## Five-minute proof

1. Send the prepared Fortuner enquiry from the console.
2. Inspect model, budget, colour, transmission, timeline, trade-in, score, inventory result, CRM status, reply mode, tool trace, audit event, and next action.
3. Create a test drive, replay the identical command, and show that one appointment exists.
4. Request a ₹50,000 discount and show that the assistant stops at a pending manager approval.
5. Disable the synthetic DMS, ask for stock, and show explicit safe fallback with no fabricated availability.
6. Send the braking-noise service scenario and show the high-priority service queue.
7. Queue a stale high-intent lead and finish on the grounded manager briefing.

Detailed presenter notes are in [docs/demo-script.md](docs/demo-script.md).

## What AI does—and does not do

| Capability | AI-assisted | Deterministic control |
|---|---:|---:|
| Interpret customer language and formulate a concise reply | Yes | Fallback remains available |
| Search inventory through a validated read-only tool | Yes | Query and result source are bounded |
| Extract core demo lead fields | Optional enrichment | Baseline extraction and scoring |
| Create or replay a booking | No | Typed command + idempotency key |
| Approve a material discount | No | Named threshold + human decision |
| Write business records | No | Domain services and CRM adapter |
| Claim stock during a DMS outage | No | Grounding guard rejects the claim |

The model receives no database connection and no unrestricted mutation tool. Tool names are allow-listed, arguments pass Pydantic validation, provider failures are categorized, and generated mutation, stock, and price claims are guarded before delivery.

## Operational surfaces

- Normalized inbound channel events with durable replay receipts
- Structured lead context and named lead-scoring inputs
- Verified synthetic inventory matches and DMS failure state
- Appointment creation with booking and webhook idempotency
- Service safety classification and preferred-time capture
- Discount approval request and manager decision lifecycle
- Airtable upsert ledger with record links, retries, and failure status
- Stale high-intent lead detection and recovery state
- Grounded manager exception briefing
- Audit timeline and model/tool trace
- Eight credential-free n8n workflow exports
- Browser voice adapter clearly labelled as a demo transport

## Run locally

Requirements: Docker with Compose, or Python 3.11+ with uv.

~~~bash
git clone <repository-url>
cd customer-ops-ai
cp .env.example .env
docker compose up -d --build
~~~

The .env file is optional for deterministic/mock mode and is ignored by Git. Never commit it.

Open:

- Console: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- Liveness/provider state: http://localhost:8000/health
- Database readiness: http://localhost:8000/ready

Useful commands:

~~~bash
make verify
make eval
make providers  # live NIM and Airtable preflight; requires local credentials
make logs
make down
make clean  # destructive: removes the local demo database volume
~~~

## Configuration

All secrets stay in environment variables or a local secret store.

| Variable | Required | Purpose |
|---|---:|---|
| DATABASE_URL | Container-provided | PostgreSQL/SQLAlchemy connection |
| NVIDIA_NIM_API_KEY | For live NIM | Provider credential |
| NVIDIA_NIM_BASE_URL | No | OpenAI-compatible endpoint |
| NVIDIA_NIM_MODEL | No | Account-available model ID |
| NVIDIA_NIM_TIMEOUT_SECONDS | No | Per-request timeout |
| NVIDIA_NIM_MAX_RETRIES | No | Bounded retry count |
| AIRTABLE_API_KEY | For live CRM | Airtable PAT |
| AIRTABLE_BASE_ID | For live CRM | CRM base |
| AIRTABLE_ENABLED | For live CRM | Explicit live-write switch |
| AIRTABLE_*_TABLE | No | Configurable table-name mapping |
| ADMIN_API_KEY | Recommended when deployed | Protects manager/admin mutations |

NIM and Airtable default to safe fallback/mock behavior. The health endpoint reports which mode is active. Live NIM chat and inventory tool calling were verified with `z-ai/glm-5.3-flash` through NVIDIA's hosted endpoint; the model remains configurable because hosted catalogs change. See [docs/airtable-setup.md](docs/airtable-setup.md) for the exact CRM schema.

## n8n orchestration

The n8n directory contains workflows for:

1. inbound normalization and lead routing,
2. appointment confirmation and duplicate suppression,
3. service-case routing,
4. approval decision callback,
5. lost-lead recovery,
6. provider error handling,
7. manager briefing,
8. system-health alerts.

They contain no credentials and keep policy in the control layer rather than Code or Function nodes. All eight exports were CLI-imported successfully into n8n 2.38.7, and the Manager Briefing was executed end to end against the live Compose API. Setup notes are in [n8n/README.md](n8n/README.md).

## Verification

~~~bash
uv sync --extra dev
make verify
docker compose up -d --build
make eval
make providers
~~~

Current reproducible results:

- 24 automated policy, API, idempotency, provider-failure, and adversarial tests
- 11/11 live Docker/PostgreSQL demo checks
- 300 deterministic synthetic inventory rows after first seed
- 8/8 credential-free n8n exports validated and imported on n8n 2.38.7; manager briefing executed successfully

The evals report actual pass/fail checks; no quality percentage is inferred from this small scenario suite. See [docs/evals.md](docs/evals.md).

## Reliability and governance

~~~mermaid
sequenceDiagram
    participant Customer
    participant API as Control layer
    participant AI as NVIDIA NIM
    participant DMS as Synthetic DMS
    participant Human as Manager

    Customer->>API: Enquiry or command
    API->>DMS: Verified read
    alt DMS available
        DMS-->>API: Bounded results
        API->>AI: Untrusted text + verified context
        AI-->>API: Reply or read-only tool request
        API-->>Customer: Guarded response
    else DMS unavailable
        API-->>Customer: Cannot verify; state preserved
    end
    Customer->>API: Large discount request
    API->>Human: Pending approval
    Human->>API: Typed approve, modify, or reject
~~~

Design rationale and threat boundaries are documented in [docs/architecture.md](docs/architecture.md), [docs/decisions.md](docs/decisions.md), and [docs/threat-model.md](docs/threat-model.md).

## Real versus simulated

| Area | Repository implementation | Production replacement |
|---|---|---|
| Messaging | Browser/demo webhook transport | WhatsApp Cloud API or another provider |
| Voice | Browser Web Speech adapter | Twilio, Exotel, or contact-centre telephony |
| CRM | Real Airtable adapter; mock default | Airtable, HubSpot, Salesforce, dealer CRM |
| DMS | PostgreSQL synthetic inventory | Dealer/DMS API adapter |
| AI | Real NIM HTTP adapter; deterministic fallback | Same contract or another compatible provider |
| Automation | Importable n8n workflows | Managed/self-hosted n8n with provider credentials |

## Known production gaps

This is a disciplined reference system, not a claim of production deployment. A real rollout still needs Alembic-managed upgrades, queue-backed outbox delivery, formal RBAC and identity, encrypted secrets management, OpenTelemetry export, rate limiting, PII retention and redaction policy, vendor-specific DMS and messaging adapters, load testing, and security review.

## Repository map

~~~text
app/
  main.py                  typed HTTP boundary and operations queries
  models/                  inventory and durable operational state
  providers/               NVIDIA NIM and Airtable adapters
  services/                policy, idempotency, orchestration, CRM sync
  static/index.html        zero-build operations console
n8n/                       eight business-readable workflow exports
scripts/
  seed_demo.py             deterministic synthetic data
  run_demo_eval.py         live stack scenario runner
  secret_scan.py           value-suppressing source scan
  validate_workflows.py    export structure and credential check
tests/                     policy, failure, API, and adversarial coverage
docs/                      architecture, evals, threat model, demo guidance
~~~
