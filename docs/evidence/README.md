# Final service-operations demo evidence

This directory contains the public evidence used to explain the final service-operations reference implementation.

The current screenshots were captured during the final hands-on walkthrough on **2026-09-13**. Browser URL / tab chrome was removed where needed so unrelated browsing activity is not exposed. The application content itself was left intact.

## What is synthetic

All customer identities, contact details, vehicles, registrations, inventory, prices, service demand, appointment slots and operating history shown in the demo are synthetic. No real TSG, Toyota, dealership or customer data is present.

The synthetic world is deterministic: `app/demo_world.py` is seeded with fixed random seed `42`, allowing the same business constraints to be replayed and regression-tested.

## What is real implementation behavior

The screenshots correspond to real local execution paths for:

- FastAPI / Python validation and service-state handling
- PostgreSQL-backed slot availability and booking transactions
- NVIDIA NIM provider integration with bounded authority
- n8n webhook orchestration and execution metadata
- idempotent appointment creation and duplicate suppression
- Airtable API projection
- manager operations visibility

## Final evidence set

### `final/customer-confirmed.jpg`

Final customer journey after explicit confirmation. The synthetic Arjun Mehta / Innova Hycross request was booked for Monday at 10:00 in Gurugram only after the slot had been selected and the confirmation boundary crossed.

### `final/manager-overview.jpg`

Manager workspace from the same final run. It demonstrates that the system is not only a chat surface: operational metrics, intervention work, recent activity, service appointments and manager-controlled work are visible in one workspace.

### `final/n8n-inbound-execution.jpg`

Successful **Customer Enquiry Intake** execution. The executed path visibly shows the inbound webhook, event normalization, governed control-layer call, priority branch and returned channel response.

### `final/n8n-service-escalation.jpg`

**Service Escalation & Routing** workflow. It demonstrates the designed safety boundary between an immediate workshop escalation and the normal workshop queue path.

## Final walkthrough result

The clean golden run verified this path:

```text
name / vehicle onboarding
-> natural-language service request
-> Saturday primary + Monday fallback retained
-> PostgreSQL-backed slot lookup
-> unrelated mid-flow question rejected without corrupting service state
-> customer changes preference to Monday
-> explicit confirmation
-> slot revalidation
-> one transactional appointment
-> Airtable projection
-> manager dashboard visibility
-> successful n8n orchestration proof
```

The previous `Vehicle not recorded` presentation problem did not reproduce in the final run: the dynamic booking showed the expected **Innova Hycross** vehicle in both the manager dashboard and Airtable projection.

A minor presentation limitation remains visible in the CRM projection: the service-request field can retain the customer's raw sentence instead of a normalized service label. It does not affect booking authority or transaction correctness and was intentionally not expanded into a late redesign.

## Verified build evidence

At commit `d9bdc671564ee997299b191663b970d581a53939` before this documentation update:

```text
Compile                  passed
Ruff                     passed
n8n workflow exports      8 validated
Secret / history scan     passed
Tests                     61 passed
Docker image build        passed
```

The final walkthrough additionally confirmed the configured NVIDIA NIM provider, PostgreSQL-backed service facts, Airtable projection and the n8n booking execution path.

## Privacy and presentation

The committed images are intentionally limited to synthetic demo content and workflow UI. They should not contain API keys, credentials, cookies, browser addresses, unrelated personal tabs, or real customer information.

Older files directly under `docs/evidence/` are retained as archived pre-pivot evidence from the earlier sales-oriented interface. They are historical artifacts and should not be treated as the current service-operations screenshots.
