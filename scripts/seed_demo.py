import random
from datetime import datetime, time, timedelta

from app.core.time import utcnow
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.demo_world import BRANCHES, CATALOG, COLOURS
from app.models import (
    Appointment,
    ApprovalRequest,
    AuditEvent,
    Customer,
    CustomerProfile,
    Interaction,
    Lead,
    ServiceBookingContext,
    ServiceRequest,
    ServiceSlot,
    SystemState,
    VehicleInventory,
)
from app.services.service_scheduling import demo_today, next_weekday, seed_service_slots

random.seed(42)


def seed_inventory(db):
    if db.query(VehicleInventory).count() > 0:
        return
    stock_number = 1
    for model, variants in CATALOG.items():
        for _ in range(30):
            variant, fuel, transmission, price = random.choice(variants)
            branch = random.choice(BRANCHES)
            db.add(
                VehicleInventory(
                    stock_id=f"{branch[:3].upper()}-{model[:3].upper().replace(' ', '')}-{stock_number:05d}",
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
            stock_number += 1


def _customer(db, name, phone, email, vehicle, registration, branch="Gurugram"):
    customer = Customer(name=name, phone=phone, email=email, created_at=utcnow() - timedelta(days=20))
    db.add(customer)
    db.flush()
    db.add(
        CustomerProfile(
            customer_id=customer.id,
            vehicle_model=vehicle,
            registration=registration,
            preferred_branch=branch,
            current_status="ACTIVE",
        )
    )
    return customer


def _lead(db, customer, intent, stage, summary, *, score=35, age_minutes=30):
    created_at = utcnow() - timedelta(minutes=age_minutes)
    lead = Lead(
        customer_id=customer.id,
        source_event_id=f"seed-lead-{customer.id}",
        source_channel="demo-baseline",
        intent=intent,
        lead_score=score,
        stage=stage,
        summary=summary,
        crm_sync_status="NOT_SYNCED",
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(lead)
    db.flush()
    db.add(
        Interaction(
            customer_id=customer.id,
            lead_id=lead.id,
            channel="demo-baseline",
            direction="INBOUND",
            content=summary,
            intent=intent,
            event_id=f"seed-message-{customer.id}",
            created_at=created_at,
        )
    )
    return lead


def _service_request(db, customer, message, urgency, stage, preferred_time):
    request = ServiceRequest(
        customer_id=customer.id,
        source_event_id=f"seed-service-{customer.id}",
        vehicle_model=db.query(CustomerProfile).filter_by(customer_id=customer.id).one().vehicle_model,
        registration=db.query(CustomerProfile).filter_by(customer_id=customer.id).one().registration,
        issue_summary=message,
        urgency=urgency,
        stage=stage,
        preferred_time_text=preferred_time,
        created_at=utcnow() - timedelta(minutes=35 if urgency != "NORMAL" else 10),
    )
    db.add(request)
    db.flush()
    return request


def seed_operations(db):
    if db.query(Customer).count() > 0:
        return
    today = demo_today()
    monday = next_weekday("monday", today=today)

    sarah = _customer(db, "Sarah Patel", "+919900000001", "sarah@example.com", "Urban Cruiser Hyryder", "DL01SP4000")
    sarah_lead = _lead(
        db,
        sarah,
        "service",
        "SERVICE_ESCALATED",
        "Brake grinding concern requires workshop advisor review.",
        age_minutes=35,
    )
    _service_request(db, sarah, "Grinding noise when braking", "HIGH", "NEEDS_ADVISOR", None)

    for index, (name, vehicle, registration, hour) in enumerate(
        [
            ("Riya Verma", "Innova Hycross", "DL01RV4001", 10),
            ("Vikram Singh", "Fortuner", "HR26VS4002", 14),
            ("Neha Gupta", "Glanza", "DL03NG4003", 16),
        ]
    ):
        customer = _customer(db, name, f"+91990000010{index}", f"service{index}@example.com", vehicle, registration)
        lead = _lead(db, customer, "service", "SERVICE_BOOKED", "Routine service confirmed through typed booking.")
        request = _service_request(db, customer, "Routine scheduled service", "NORMAL", "BOOKED", "Today")
        db.add(
            ServiceBookingContext(
                lead_id=lead.id,
                service_request_id=request.id,
                requested_service="Scheduled vehicle service",
                requested_branch="Gurugram",
                requested_date=datetime.combine(today, time.min),
                status="BOOKED",
            )
        )
        db.add(
            Appointment(
                lead_id=lead.id,
                kind="service",
                branch="Gurugram",
                scheduled_for=datetime.combine(today, time(hour, 0)),
                status="COMPLETED" if index == 2 else "BOOKED",
                idempotency_key=f"seed-service-appointment-{index}",
                created_at=utcnow() - timedelta(hours=2 + index),
            )
        )

    ananya = _customer(db, "Ananya Mehta", "+919900000020", "ananya@example.com", "Camry", "DL04AM4004")
    ananya_lead = _lead(db, ananya, "service", "NEW", "Monday service alternative awaiting customer confirmation.")
    ananya_request = _service_request(db, ananya, "40,000 km scheduled service", "NORMAL", "OPEN", "Monday 14:00")
    slot = next(
        item
        for item in db.query(ServiceSlot).all()
        if item.branch == "Gurugram" and item.starts_at.date() == monday and item.starts_at.hour == 14
    )
    db.add(
        ServiceBookingContext(
            lead_id=ananya_lead.id,
            service_request_id=ananya_request.id,
            requested_service="40,000 km scheduled service",
            requested_branch="Gurugram",
            requested_date=datetime.combine(monday, time.min),
            selected_slot_id=slot.id,
            status="AWAITING_CONFIRMATION",
        )
    )

    rohan = _customer(db, "Rohan Kapoor", "+919900000030", "rohan@example.com", "", "")
    sales_lead = _lead(db, rohan, "sales", "QUALIFIED", "Secondary proof: verified Hyryder enquiry.", score=82, age_minutes=90)
    sales_lead.model_interest = "Urban Cruiser Hyryder"

    ishita = _customer(db, "Ishita Bansal", "+919900000040", "ishita@example.com", "", "")
    approval_lead = _lead(db, ishita, "sales", "QUALIFIED", "Commercial request paused for manager approval.", score=75)
    db.add(
        ApprovalRequest(
            lead_id=approval_lead.id,
            action="discount",
            requested_value="50000",
            recommendation="Human approval required. Synthetic demo request.",
            status="PENDING",
        )
    )

    aditya = _customer(db, "Aditya Sharma", "+919900000050", "aditya@example.com", "Innova Crysta", "DL05AS4005")
    _lead(db, aditya, "support", "HUMAN_HANDOFF_REQUESTED", "Customer asked to speak with a service advisor.")

    db.add(
        AuditEvent(
            event_type="demo.seeded",
            entity_type="system",
            entity_id="demo",
            payload={"customers": 8, "focus": "service_operations", "synthetic": True},
        )
    )
    db.add(
        AuditEvent(
            event_type="service.safety_escalated",
            entity_type="lead",
            entity_id=str(sarah_lead.id),
            payload={"urgency": "HIGH", "advisor_required": True},
        )
    )


def seed_system_states(db):
    for service in ["inventory", "crm", "messaging", "scheduler"]:
        if not db.query(SystemState).filter_by(service_name=service).first():
            db.add(SystemState(service_name=service, is_available=True))


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_inventory(db)
        seed_system_states(db)
        seed_service_slots(db)
        db.flush()
        seed_operations(db)
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
