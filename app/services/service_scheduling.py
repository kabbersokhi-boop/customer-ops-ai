import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, ServiceBookingContext, ServiceRequest, ServiceSlot
from app.services.service_requests import create_service_request, extract_preferred_time

DEMO_TIMEZONE = ZoneInfo("Asia/Kolkata")
DEFAULT_BRANCH = "Gurugram"
BRANCH_ALIASES = {
    "gurugram": "Gurugram",
    "gurgaon": "Gurugram",
    "noida": "Noida",
    "new delhi": "New Delhi",
    "delhi": "New Delhi",
    "faridabad": "Faridabad",
    "ghaziabad": "Ghaziabad",
}
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def demo_today() -> date:
    return datetime.now(DEMO_TIMEZONE).date()


def next_weekday(day_name: str, *, today: date | None = None) -> date:
    current = today or demo_today()
    target = WEEKDAYS[day_name.lower()]
    delta = (target - current.weekday()) % 7
    return current + timedelta(days=delta or 7)


def seed_service_slots(db: Session, *, today: date | None = None) -> None:
    current = today or demo_today()
    saturday = next_weekday("saturday", today=current)
    monday = next_weekday("monday", today=current)
    definitions = [
        ("Gurugram", datetime.combine(saturday, time(10, 0)), 1, 1),
        ("Gurugram", datetime.combine(saturday, time(14, 0)), 1, 1),
        ("Noida", datetime.combine(saturday, time(14, 30)), 1, 0),
        ("Gurugram", datetime.combine(monday, time(10, 0)), 1, 0),
        ("Gurugram", datetime.combine(monday, time(14, 0)), 1, 0),
        ("Noida", datetime.combine(monday, time(11, 30)), 1, 0),
    ]
    for branch, starts_at, capacity, booked_count in definitions:
        existing = db.scalar(
            select(ServiceSlot).where(ServiceSlot.branch == branch, ServiceSlot.starts_at == starts_at)
        )
        if not existing:
            db.add(
                ServiceSlot(
                    branch=branch,
                    starts_at=starts_at,
                    capacity=capacity,
                    booked_count=booked_count,
                )
            )


def slot_dict(slot: ServiceSlot) -> dict:
    return {
        "slot_id": slot.id,
        "branch": slot.branch,
        "starts_at": slot.starts_at.isoformat(),
        "label": f"{slot.starts_at.strftime('%A, %d %b')} at {slot.starts_at.strftime('%H:%M')}",
        "remaining_capacity": max(slot.capacity - slot.booked_count, 0),
    }


def available_slots(
    db: Session,
    *,
    branch: str | None = None,
    requested_date: date | None = None,
    limit: int = 8,
) -> list[ServiceSlot]:
    stmt = select(ServiceSlot).where(
        ServiceSlot.is_active.is_(True),
        ServiceSlot.capacity > ServiceSlot.booked_count,
        ServiceSlot.starts_at >= datetime.combine(demo_today(), time.min),
    )
    if branch:
        stmt = stmt.where(ServiceSlot.branch == branch)
    if requested_date:
        stmt = stmt.where(
            ServiceSlot.starts_at >= datetime.combine(requested_date, time.min),
            ServiceSlot.starts_at < datetime.combine(requested_date + timedelta(days=1), time.min),
        )
    return list(db.scalars(stmt.order_by(ServiceSlot.starts_at, ServiceSlot.branch).limit(limit)).all())


def availability_result(db: Session, *, branch: str, requested_date: date) -> dict:
    exact = available_slots(db, branch=branch, requested_date=requested_date)
    same_day_other_branch = [
        slot for slot in available_slots(db, requested_date=requested_date) if slot.branch != branch
    ]
    future_same_branch = [
        slot for slot in available_slots(db, branch=branch) if slot.starts_at.date() != requested_date
    ]
    return {
        "requested": {"branch": branch, "date": requested_date.isoformat()},
        "available": [slot_dict(slot) for slot in exact],
        "alternatives": [slot_dict(slot) for slot in (future_same_branch[:2] + same_day_other_branch[:2])],
        "source": "postgresql_service_slots",
    }


def extract_branch(message: str) -> str | None:
    low = message.lower()
    return next((value for token, value in BRANCH_ALIASES.items() if token in low), None)


def extract_requested_date(message: str) -> date | None:
    low = message.lower()
    if "tomorrow" in low:
        return demo_today() + timedelta(days=1)
    if "today" in low:
        return demo_today()
    for day_name in WEEKDAYS:
        if day_name in low:
            return next_weekday(day_name)
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", low)
    return date.fromisoformat(iso.group(1)) if iso else None


def extract_requested_hour(message: str) -> tuple[int, int] | None:
    low = message.lower()
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low)
    if match:
        hour = int(match.group(1)) % 12 + (12 if match.group(3) == "pm" else 0)
        return hour, int(match.group(2) or 0)
    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", low)
    if match:
        return int(match.group(1)), int(match.group(2))
    if re.search(r"\b10\b", low):
        return 10, 0
    if re.search(r"\b2\b", low):
        return 14, 0
    return None


def extract_service_name(message: str) -> str:
    match = re.search(r"\b(\d{1,3}(?:,\d{3})?)\s*km\b", message, re.I)
    return f"{match.group(1)} km scheduled service" if match else "Scheduled vehicle service"


def get_context(db: Session, lead_id: int | None) -> ServiceBookingContext | None:
    if not lead_id:
        return None
    return db.scalar(select(ServiceBookingContext).where(ServiceBookingContext.lead_id == lead_id))


def _reply_for_options(result: dict, requested_service: str) -> str:
    exact = result["available"]
    if exact:
        choices = ", ".join(f"{item['label']} at {item['branch']}" for item in exact)
        return f"I found these verified slots for your {requested_service}: {choices}. Which time works for you?"
    alternatives = result["alternatives"]
    requested = result["requested"]
    if not alternatives:
        return (
            f"There are no verified slots at {requested['branch']} on {requested['date']}. "
            "I have not booked anything; a service advisor can follow up."
        )
    choices = "; ".join(f"{item['label']} at {item['branch']}" for item in alternatives)
    return (
        f"{requested['branch']} is full on {requested['date']}. I have not booked anything. "
        f"Verified alternatives are: {choices}. Which option works for you?"
    )


def handle_service_booking(
    db: Session,
    *,
    lead_id: int,
    customer_name: str,
    customer_phone: str,
    message: str,
    urgency: str,
    event_id: str,
    vehicle_model: str | None = None,
) -> dict:
    context = get_context(db, lead_id)
    service_request = db.get(ServiceRequest, context.service_request_id) if context else None
    if not service_request:
        service_request, _ = create_service_request(
            db,
            name=customer_name,
            phone=customer_phone,
            message=message,
            vehicle_model=vehicle_model,
            preferred_time_text=extract_preferred_time(message),
            event_id=f"service:{event_id}",
        )
        context = ServiceBookingContext(
            lead_id=lead_id,
            service_request_id=service_request.id,
            requested_service=extract_service_name(message),
            requested_branch=extract_branch(message) or DEFAULT_BRANCH,
        )
        db.add(context)
        db.flush()

    if urgency in {"HIGH", "CRITICAL"} or service_request.urgency in {"HIGH", "CRITICAL"}:
        service_request.stage = "NEEDS_ADVISOR"
        context.status = "ESCALATED"
        db.add(
            AuditEvent(
                event_type="service.safety_escalated",
                entity_type="service_request",
                entity_id=str(service_request.id),
                payload={"urgency": service_request.urgency, "booking_blocked": True},
            )
        )
        db.commit()
        return {
            "service_request": service_request,
            "context": context,
            "reply": (
                "I’m not going to diagnose a safety-sensitive concern in chat. If the vehicle feels unsafe, "
                "stop driving and seek roadside assistance. I’ve created a priority service case for a workshop advisor; "
                "no routine appointment has been booked."
            ),
            "booking": {"status": "ESCALATED", "confirmed": False, "urgency": service_request.urgency},
        }

    branch = extract_branch(message) or context.requested_branch
    requested_date = extract_requested_date(message)
    if requested_date:
        context.requested_date = datetime.combine(requested_date, time.min)
    elif context.requested_date:
        requested_date = context.requested_date.date()
    context.requested_branch = branch
    hour = extract_requested_hour(message)

    if not requested_date:
        context.status = "COLLECTING_DATE"
        db.commit()
        return {
            "service_request": service_request,
            "context": context,
            "reply": f"I can check verified service availability at {branch}. Which day would you prefer?",
            "booking": {"status": context.status, "confirmed": False, "source": "postgresql_service_slots"},
        }

    result = availability_result(db, branch=branch, requested_date=requested_date)
    candidates = result["available"]
    if hour:
        candidates = [
            item
            for item in candidates
            if datetime.fromisoformat(item["starts_at"]).time() == time(hour[0], hour[1])
        ]
    if len(candidates) == 1:
        selected = candidates[0]
        context.selected_slot_id = selected["slot_id"]
        context.status = "AWAITING_CONFIRMATION"
        service_request.preferred_time_text = selected["label"]
        db.add(
            AuditEvent(
                event_type="service.slot_selected",
                entity_type="service_request",
                entity_id=str(service_request.id),
                payload={"slot_id": selected["slot_id"], "branch": selected["branch"], "starts_at": selected["starts_at"]},
            )
        )
        db.commit()
        return {
            "service_request": service_request,
            "context": context,
            "reply": (
                f"I’ve held the details for {context.requested_service} at {selected['branch']} on "
                f"{selected['label']}. Please review your contact details and explicitly confirm below. "
                "The appointment does not exist until that command succeeds."
            ),
            "booking": {
                "status": context.status,
                "confirmed": False,
                "service_request_id": service_request.id,
                "service": context.requested_service,
                "slot": selected,
                "idempotency_key": f"service-{service_request.id}-slot-{selected['slot_id']}",
                "source": "postgresql_service_slots",
            },
        }

    context.status = "AWAITING_SLOT_SELECTION" if result["available"] else "ALTERNATIVES_OFFERED"
    db.add(
        AuditEvent(
            event_type="service.availability_checked",
            entity_type="service_request",
            entity_id=str(service_request.id),
            payload={
                "branch": branch,
                "requested_date": requested_date.isoformat(),
                "available_count": len(result["available"]),
                "alternative_count": len(result["alternatives"]),
            },
        )
    )
    db.commit()
    return {
        "service_request": service_request,
        "context": context,
        "reply": _reply_for_options(result, context.requested_service),
        "booking": {"status": context.status, "confirmed": False, **result},
    }
