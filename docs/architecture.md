# Architecture

## Design objective

Insert language-model reasoning into customer operations while keeping data authority, mutations, commercial policy, and failure recovery explicit.

~~~mermaid
flowchart TB
    subgraph Channels
      M[Demo messaging]
      V[Browser voice demo]
      W[Provider webhook]
    end
    subgraph Orchestration
      N[n8n workflows]
    end
    subgraph Control
      A[FastAPI typed API]
      G[Grounding guard]
      P[Policy and idempotency]
    end
    subgraph Providers
      L[NVIDIA NIM]
      R[Airtable CRM]
      D[(PostgreSQL synthetic DMS)]
    end
    M --> N
    V --> N
    W --> N
    N --> A
    A --> P
    A --> L
    L --> G
    G --> A
    A --> R
    A --> D
~~~

## Trust boundaries

### Channel boundary

Every transport becomes one normalized event with a provider event ID. A durable receipt stores the original response, so a replay returns the prior business result without duplicating interactions or CRM work.

### LLM boundary

Customer text is untrusted. NVIDIA NIM can formulate a response and request an allow-listed read-only inventory tool. Tool arguments pass schema validation. The model receives neither database credentials nor mutation tools.

### Mutation boundary

Bookings, approval decisions, recovery state, and failure simulation are typed application commands. Booking and inbound-event retries carry idempotency keys. Inventory can be rechecked at booking time to catch state changes.

### DMS boundary

Inventory is queried from PostgreSQL through one bounded service. When disabled, reads return a structured unavailable result and the response guard suppresses availability claims.

### CRM boundary

Airtable is an adapter behind provider-neutral mappings. Customer, lead, activity, appointment, and approval records are upserted. Provider errors are categorized and stored without replacing domain truth.

### Orchestration boundary

n8n normalizes, routes, schedules, retries, and hands off to delivery providers. Core scoring, idempotency, inventory truth, and discount policy stay in tested Python services.

## Failure semantics

| Failure | Safe behavior |
|---|---|
| Duplicate inbound event | Return the stored response |
| Duplicate booking | Return the existing appointment |
| DMS unavailable | Preserve lead; suppress stock claims |
| CRM unavailable | Preserve domain state; record failed sync |
| NIM timeout/error | Deterministic reply with visible provider code |
| Malformed tool arguments | Reject tool call; expose trace |
| Model claims a booking/discount | Replace with deterministic response |
| Vehicle changes before booking | Reject with a structured conflict |

## Data ownership

- PostgreSQL: operational and synthetic inventory truth
- Airtable: CRM projection
- n8n: orchestration executions
- NVIDIA NIM: stateless reasoning provider
- Browser: explicitly simulated transport
