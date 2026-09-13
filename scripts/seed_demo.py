import random
from datetime import timedelta

from app.core.time import utcnow
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.demo_world import BRANCHES, CATALOG, COLOURS
from app.models import (
    Appointment,
    ApprovalRequest,
    AuditEvent,
    Customer,
    Interaction,
    Lead,
    ServiceRequest,
    SystemState,
    VehicleInventory,
)

random.seed(42)

FIRST_NAMES = ["Arjun", "Riya", "Kabir", "Meera", "Rohan", "Ananya", "Vikram", "Ishita", "Aditya", "Neha"]
LAST_NAMES = ["Sharma", "Verma", "Kapoor", "Singh", "Malhotra", "Gupta", "Mehta", "Bansal"]


def seed_inventory(db):
    if db.query(VehicleInventory).count() > 0:
        return
    i = 1
    for model, variants in CATALOG.items():
        for _ in range(30):
            variant, fuel, transmission, price = random.choice(variants)
            branch = random.choice(BRANCHES)
            db.add(
                VehicleInventory(
                    stock_id=f"{branch[:3].upper()}-{model[:3].upper().replace(' ', '')}-{i:05d}",
                    model=model,
                    variant=variant,
                    fuel_type=fuel,
                    transmission=transmission,
                    colour=random.choice(COLOURS),
                    branch=branch,
                    demo_price_inr=int(price * random.uniform(0.98, 1.02)),
                    status=random.choices(["AVAILABLE", "RESERVED"], weights=[9, 1])[0],
                    test_drive_vehicle=random.random() < 0.12,
                    expected_delivery_days=random.choice([0, 3, 5, 7, 10, 14, 21]),
                )
            )
            i += 1


def seed_operations(db):
    if db.query(Customer).count() > 0:
        return

    now = utcnow()
    leads = []
    for i in range(60):
        customer = Customer(
            name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            phone=f"+9198{i:08d}",
            email=f"demo{i}@example.com",
            created_at=now - timedelta(days=random.randint(1, 30)),
        )
        db.add(customer)
        db.flush()
        model = random.choice(list(CATALOG))
        score = random.randint(45, 98)
        age_hours = random.randint(2, 120)
        stage = "QUALIFIED" if score >= 70 else "NEW"
        lead = Lead(
            customer_id=customer.id,
            source_event_id=f"seed-lead-{i}",
            source_channel=random.choice(["whatsapp-demo", "web", "browser_voice"]),
            intent="sales",
            model_interest=model,
            budget_inr=random.choice([1_500_000, 2_000_000, 3_000_000, 4_500_000, 5_000_000]),
            colour_preference=random.choice(["White", "Black", "Silver", None]),
            transmission_preference=random.choice(["Automatic", "Automatic", "Manual"]),
            timeline_days=random.choice([7, 14, 30, 60]),
            trade_in_vehicle=random.choice([None, None, "Hyundai Creta", "Maruti Swift", "Mahindra XUV500"]),
            lead_score=score,
            stage=stage,
            summary=f"Synthetic {model} enquiry generated for dashboard demonstration.",
            crm_sync_status="MOCK",
            created_at=now - timedelta(hours=age_hours + random.randint(1, 24)),
            updated_at=now - timedelta(hours=age_hours),
        )
        db.add(lead)
        db.flush()
        leads.append(lead)
        db.add(
            Interaction(
                customer_id=customer.id,
                lead_id=lead.id,
                channel=lead.source_channel,
                direction="INBOUND",
                content=f"I am interested in a {model} and would like more information.",
                intent="sales",
                event_id=f"seed-msg-{i}",
                created_at=lead.created_at,
            )
        )

    # Book some leads so the lost-lead detector has a meaningful contrast.
    for idx, lead in enumerate(leads[:16]):
        lead.stage = "TEST_DRIVE_BOOKED"
        lead.updated_at = now - timedelta(hours=random.randint(1, 18))
        db.add(
            Appointment(
                lead_id=lead.id,
                kind="test_drive",
                branch=random.choice(BRANCHES),
                scheduled_for=now + timedelta(days=random.randint(1, 7), hours=random.randint(9, 17)),
                status="BOOKED",
                idempotency_key=f"seed-appt-{idx}",
                created_at=now - timedelta(hours=random.randint(1, 24)),
            )
        )

    for lead in leads[16:21]:
        db.add(
            ApprovalRequest(
                lead_id=lead.id,
                action="discount",
                requested_value=str(random.choice([25_000, 40_000, 50_000])),
                recommendation="Human approval required. Synthetic demo request.",
                status="PENDING",
                created_at=now - timedelta(hours=random.randint(1, 12)),
            )
        )

    for i in range(12):
        customer = db.query(Customer).filter(Customer.id == leads[-(i + 1)].customer_id).one()
        db.add(
            ServiceRequest(
                customer_id=customer.id,
                source_event_id=f"seed-service-{i}",
                vehicle_model=random.choice(["Fortuner", "Urban Cruiser Hyryder", "Innova Hycross"]),
                registration=f"DL01DEMO{i:04d}",
                issue_summary=random.choice(
                    [
                        "Routine periodic service requested.",
                        "Customer reports noise when braking.",
                        "Warning light visible on dashboard.",
                    ]
                ),
                urgency="HIGH" if i in {1, 4} else "NORMAL",
                stage="OPEN",
                preferred_time_text="Saturday morning",
                created_at=now - timedelta(hours=random.randint(2, 48)),
            )
        )

    db.add(
        AuditEvent(
            event_type="demo.seeded",
            entity_type="system",
            entity_id="demo",
            payload={"customers": 60, "note": "Synthetic operational history"},
            created_at=now,
        )
    )


def seed_system_states(db):
    for service in ["inventory", "crm", "messaging"]:
        if not db.query(SystemState).filter_by(service_name=service).first():
            db.add(SystemState(service_name=service, is_available=True))


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_inventory(db)
        seed_operations(db)
        seed_system_states(db)
        db.commit()
        print(
            "Demo seed ready:",
            {
                "inventory": db.query(VehicleInventory).count(),
                "customers": db.query(Customer).count(),
                "leads": db.query(Lead).count(),
                "appointments": db.query(Appointment).count(),
                "service_requests": db.query(ServiceRequest).count(),
                "approvals": db.query(ApprovalRequest).count(),
            },
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
