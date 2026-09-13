from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, CustomerProfile, ServiceRequest
from app.services.leads import get_or_create_customer


def infer_urgency(message: str) -> str:
    low = " ".join(message.lower().split())
    critical = [
        "brake failure",
        "cannot stop",
        "can't stop",
        "cant stop",
        "smoke",
        "fire",
        "engine overheating",
        "won't start",
        "wont start",
        "will not start",
    ]
    high = [
        "brake",
        "warning light",
        "breakdown",
        "broke down",
        "broken down",
        "stranded",
        "unsafe",
        "noise when braking",
        "not drivable",
        "undrivable",
        "cannot drive",
        "can't drive",
        "cant drive",
        "stuck on the road",
        "stuck roadside",
        "stalled",
        "engine stalled",
        "flat tyre",
        "flat tire",
        "puncture",
        "dead battery",
        "battery dead",
    ]
    if any(term in low for term in critical):
        return "CRITICAL"
    if any(term in low for term in high):
        return "HIGH"
    return "NORMAL"


def extract_preferred_time(message: str) -> str | None:
    low = message.lower()
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    matches = [(low.find(value), value) for value in days if value in low]
    day = min(matches)[1] if matches else None
    period = next((value for value in ["morning", "afternoon", "evening"] if value in low), None)
    if day and period:
        return f"{day.title()} {period}"
    if day:
        return day.title()
    if period:
        return period.title()
    return None


def create_service_request(
    db: Session,
    *,
    name: str,
    phone: str,
    message: str,
    vehicle_model: str | None = None,
    registration: str | None = None,
    preferred_time_text: str | None = None,
    event_id: str | None = None,
) -> tuple[ServiceRequest, bool]:
    if event_id:
        existing = db.scalar(select(ServiceRequest).where(ServiceRequest.source_event_id == event_id))
        if existing:
            return existing, False

    customer = get_or_create_customer(db, name, phone)
    if vehicle_model or registration:
        profile = db.scalar(select(CustomerProfile).where(CustomerProfile.customer_id == customer.id))
        if not profile:
            profile = CustomerProfile(
                customer_id=customer.id,
                vehicle_model=vehicle_model,
                registration=registration,
            )
            db.add(profile)
        else:
            if vehicle_model:
                profile.vehicle_model = vehicle_model
            if registration:
                profile.registration = registration

    request = ServiceRequest(
        customer_id=customer.id,
        source_event_id=event_id,
        vehicle_model=vehicle_model,
        registration=registration,
        issue_summary=message[:2000],
        urgency=infer_urgency(message),
        preferred_time_text=preferred_time_text,
    )
    db.add(request)
    db.flush()
    db.add(
        AuditEvent(
            event_type="service_request.created",
            entity_type="service_request",
            entity_id=str(request.id),
            payload={"urgency": request.urgency, "event_id": event_id},
        )
    )
    db.commit()
    db.refresh(request)
    return request, True
