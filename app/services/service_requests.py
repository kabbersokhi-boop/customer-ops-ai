from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, ServiceRequest
from app.services.leads import get_or_create_customer


def infer_urgency(message: str) -> str:
    low = message.lower()
    critical = ["brake failure", "cannot stop", "smoke", "fire", "engine overheating", "won't start", "wont start"]
    high = ["brake", "warning light", "breakdown", "stranded", "unsafe", "noise when braking"]
    if any(term in low for term in critical):
        return "CRITICAL"
    if any(term in low for term in high):
        return "HIGH"
    return "NORMAL"


def extract_preferred_time(message: str) -> str | None:
    low = message.lower()
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    day = next((value for value in days if value in low), None)
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
