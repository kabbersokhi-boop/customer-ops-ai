# Bounded synthetic dealership world

The data is synthetic. The workflow, policy, idempotency, failure, and integration behavior is real.

The authoritative machine-readable definition is `app/demo_world.py` and `GET /api/demo/world`. `scripts/seed_demo.py` uses that definition with random seed `42`.

## Inventory catalogue

The first seed creates **300 rows: exactly 30 units for each of 10 models**.

| Model | Possible synthetic variants | Units |
|---|---|---:|
| Fortuner | 4x2 AT; 4x4 AT | 30 |
| Legender | 4x2 AT | 30 |
| Camry | Hybrid | 30 |
| Innova Hycross | VX Hybrid; GX | 30 |
| Innova Crysta | GX | 30 |
| Urban Cruiser Hyryder | V Hybrid; G NeoDrive | 30 |
| Glanza | V AMT | 30 |
| Taisor | V Turbo AT | 30 |
| Rumion | V AT | 30 |
| Hilux | High AT | 30 |

Branches: Gurugram, New Delhi, Noida, Faridabad, Ghaziabad.

Colours: Super White, Pearl White, Attitude Black, Silver Metallic, Grey Metallic, Red, Blue, Bronze.

Every inventory row contains a synthetic stock ID, model, variant, fuel type, transmission, colour, branch, demo price, `AVAILABLE` or `RESERVED` state, test-drive flag, and expected delivery of 0, 3, 5, 7, 10, 14, or 21 days.

Variant, branch, colour, small price variation, availability, test-drive flag, and delivery days are chosen deterministically from the fixed seed. These are fictional demonstration values, not manufacturer or dealer claims.

## Operational baseline

The first seed also creates:

- 8 synthetic customers and operator-relevant interactions
- 5 service requests, including one safety-sensitive case
- 3 service appointments scheduled for today
- 1 customer awaiting service confirmation
- 1 pending discount approval and secondary sales/handoff examples
- 4 available system-state flags: inventory, CRM, messaging, and scheduler

Service availability is structured in PostgreSQL. The rolling interview fixture keeps Gurugram full on Saturday, Gurugram available Monday at 10:00 and 14:00, and Noida available Saturday at 14:30.

Subsequent demo runs add records. `make demo-reset` is the only intentional reset path; it requires an explicit confirmation phrase, rejects non-local databases, and snapshots application-owned Airtable tables before cleanup.

## Explicitly outside scope

- real Toyota, manufacturer, dealer, customer, inventory, pricing, or service-history data
- real WhatsApp messages or a WhatsApp Cloud API connection
- production telephony or call-centre integration
- a production dealer-management-system adapter
- approved warranty or policy retrieval
- arbitrary model specifications such as mileage or horsepower
- live lender rates, EMI quotations, credit decisions, or finance approvals
- arbitrary vehicle models outside the ten-model catalogue

Unsupported questions are not handed to model memory as if it were an approved knowledge source. The control layer either clarifies, explains the bounded scope, or routes to a human.
