# Final service-operations demo evidence

This directory contains the public evidence used by the repository landing page. The nine files in **final/** are the original full-resolution PNG captures supplied for the final presentation. They are committed without JPEG or WebP conversion.

## Scope and provenance

The captures document a local final walkthrough on 2026-09-13. Browser tab and URL chrome were removed where applicable. The screenshots contain only synthetic demonstration data and workflow UI.

No TSG private systems, customer data, dealer data, Toyota data, production WhatsApp traffic, or telephony records are present. The project is a capability demonstration for an AI Automation and Integration Manager opportunity; it is not a commissioned TSG implementation.

## What is synthetic

- Customer identities, contact details, vehicles, registrations, inventory, price values, service demand, appointment slots, and operating history.
- The deterministic dealership world defined in **app/demo_world.py** with fixed random seed 42.
- The service fixture: Gurugram is full on Saturday; Gurugram offers Monday 10:00 and 14:00; Noida offers Saturday 14:30.

This determinism allows reset, replay, and regression testing without private data.

## What uses real software paths

- FastAPI and Python validation, authorization, and service-state handling.
- PostgreSQL-backed slot checks, booking transactions, idempotency, audit records, and recovery state.
- NVIDIA NIM bounded language integration.
- n8n webhooks, control-layer calls, workflow routing, and execution metadata.
- Airtable API projection and CRM-failure recording.
- Manager operations visibility and intervention state.

## Final capture set

| File | Evidence |
|---|---|
| **final/01-customer-preference-and-grounded-slots.png** | Customer onboarding, natural-language 40,000 km service request, Saturday primary preference, Monday fallback, and verified alternatives. |
| **final/02-customer-booking-confirmed.png** | Explicit confirmation boundary and final booked service appointment. |
| **final/03-manager-operations-overview.png** | Manager KPIs, intervention queue, safety case, human handoff, commercial decision, and recent activity. |
| **final/04-manager-service-appointments-and-context.png** | Recent appointments, open service work, customer context, manager decisions, and technical context. |
| **final/05-airtable-appointments-crm-projection.png** | Airtable Appointments projection after booking; Airtable remains a replaceable prototype CRM adapter. |
| **final/06-n8n-workflow-estate.png** | The eight-workflow n8n estate. |
| **final/07-n8n-customer-enquiry-intake-execution.png** | Successful Customer Enquiry Intake execution through normalization, control layer, priority routing, and response. |
| **final/08-n8n-service-booking-execution.png** | Successful Service Booking and Confirmation execution through typed command and idempotent booking. |
| **final/09-n8n-service-escalation-routing.png** | Service Escalation and Routing workflow with a critical-safety branch. |

## Capture integrity

The committed files match the supplied originals byte-for-byte. Dimensions range from 1409×705 to 1922×971 pixels. File sizes range from 120 KB to 632 KB. The repository README references these files with exact case-sensitive relative paths and renders each as a full-width image.

Earlier files directly under **docs/evidence/** are archived pre-pivot evidence. The small legacy JPEG and WebP files in **final/** are not referenced by the landing page; the PNG set above is the current public evidence.

## Verified repository baseline

The documentation update was validated against the repository baseline:

~~~text
61 tests collected
8 credential-free n8n workflow exports validated
Ruff passed
History-aware secret scan passed
Docker image build passed
~~~
