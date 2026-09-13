import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.demo_world import CATALOG
from app.models import AuditEvent, Customer, Lead

MODELS = list(CATALOG)
COLOUR_ALIASES = {
    "super white": "Super White",
    "pearl white": "Pearl White",
    "white": "White",
    "safed": "White",
    "black": "Black",
    "kaali": "Black",
    "silver": "Silver",
    "grey": "Grey",
    "gray": "Grey",
    "red": "Red",
    "blue": "Blue",
    "bronze": "Bronze",
}


def extract_budget(message: str) -> int | None:
    lakh = re.search(
        r"(?:under|around|budget(?:\s+is)?|upto|up to)?\s*(\d+(?:\.\d+)?)\s*(?:lakh|lac|lakhs|lacs|l\b)", message, re.I
    )
    if lakh:
        return int(float(lakh.group(1)) * 100000)
    rupees = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+)", message, re.I)
    return int(rupees.group(1).replace(",", "")) if rupees else None


def extract_model(message: str) -> str | None:
    low = message.lower()
    return next((model for model in MODELS if model.lower() in low), None)


def extract_colour(message: str) -> str | None:
    low = message.lower()
    for alias, colour in COLOUR_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", low):
            return colour
    return None


def extract_transmission(message: str) -> str | None:
    low = message.lower()
    if re.search(r"\b(?:automatic|auto|at|cvt|e-cvt)\b", low):
        return "Automatic"
    if re.search(r"\b(?:manual|mt)\b", low):
        return "Manual"
    return None


def extract_timeline_days(message: str) -> int | None:
    low = message.lower()
    if "today" in low:
        return 0
    if "tomorrow" in low:
        return 1
    if "weekend" in low or "this week" in low:
        return 7
    if "this month" in low or "iss mahine" in low or "is mahine" in low:
        return 30
    match = re.search(r"(?:in|within)\s+(\d+)\s*(day|days|week|weeks|month|months)", low)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("week"):
        amount *= 7
    elif unit.startswith("month"):
        amount *= 30
    return amount


def extract_trade_in(message: str) -> str | None:
    low = message.lower()
    if not any(term in low for term in ["exchange", "trade-in", "trade in", "trade"]):
        return None
    patterns = [
        r"(?:exchange|trade[- ]?in|trade)\s+(?:my\s+)?([a-z0-9 -]{2,40})",
        r"(?:have|got)\s+(?:a|an|my)\s+([a-z0-9 -]{2,40})\s+to\s+(?:exchange|trade)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.I)
        if match:
            value = re.split(r"[,.]|\band\b|\bfor\b", match.group(1), maxsplit=1, flags=re.I)[0].strip()
            return value.title()[:120] or "Trade-in vehicle"
    return "Trade-in vehicle"


def infer_intent(message: str) -> str:
    low = message.lower()
    service_terms = [
        "service",
        "servicing",
        "repair",
        "brake",
        "noise",
        "oil change",
        "maintenance",
        "workshop",
        "awaaz",
    ]
    support_terms = ["complaint", "refund", "cancel booking", "problem with booking"]
    if any(term in low for term in service_terms):
        return "service"
    if any(term in low for term in support_terms):
        return "support"
    sales_terms = [
        "car",
        "vehicle",
        "suv",
        "buy",
        "purchase",
        "budget",
        "lakh",
        "test drive",
        "book",
        "appointment",
        "showroom",
        "discount",
        "warranty",
        "mileage",
        "finance",
    ]
    if extract_model(message) or any(term in low for term in sales_terms):
        return "sales"
    return "general"


def score_lead(message: str, model: str | None, budget: int | None, timeline_days: int | None) -> int:
    if infer_intent(message) != "sales":
        return 0
    score = 25
    low = message.lower()
    if model:
        score += 20
    if budget:
        score += 15
    if timeline_days is not None:
        score += 15 if timeline_days <= 30 else 8
    if any(k in low for k in ["test drive", "book", "appointment", "visit showroom", "dekhna hai"]):
        score += 15
    if any(k in low for k in ["exchange", "trade", "finance", "loan"]):
        score += 5
    if any(k in low for k in ["buy", "purchase", "ready to book"]):
        score += 5
    return min(score, 100)


def get_or_create_customer(db: Session, name: str, phone: str) -> Customer:
    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if customer:
        if name and customer.name != name:
            customer.name = name
        return customer
    customer = Customer(name=name, phone=phone)
    db.add(customer)
    db.flush()
    return customer


def intake_lead(
    db: Session,
    name: str,
    phone: str,
    message: str,
    channel: str,
    event_id: str | None = None,
    conversation_lead_id: int | None = None,
) -> tuple[Lead, bool]:
    if event_id:
        existing = db.scalar(select(Lead).where(Lead.source_event_id == event_id))
        if existing:
            return existing, False

    customer = get_or_create_customer(db, name, phone)
    model = extract_model(message)
    budget = extract_budget(message)
    timeline_days = extract_timeline_days(message)
    colour = extract_colour(message)
    transmission = extract_transmission(message)
    trade_in = extract_trade_in(message)
    intent = infer_intent(message)
    score = score_lead(message, model, budget, timeline_days) if intent == "sales" else 35

    continued = db.get(Lead, conversation_lead_id) if conversation_lead_id else None
    if continued and continued.customer_id == customer.id:
        continued.model_interest = model or continued.model_interest
        continued.budget_inr = budget or continued.budget_inr
        continued.colour_preference = colour or continued.colour_preference
        continued.transmission_preference = transmission or continued.transmission_preference
        continued.timeline_days = timeline_days if timeline_days is not None else continued.timeline_days
        continued.trade_in_vehicle = trade_in or continued.trade_in_vehicle
        if intent != "general":
            continued.intent = intent
        accumulated_score = score_lead(
            message,
            continued.model_interest,
            continued.budget_inr,
            continued.timeline_days,
        )
        continued.lead_score = max(continued.lead_score, accumulated_score)
        if continued.stage in {"NEW", "QUALIFIED"}:
            continued.stage = "QUALIFIED" if continued.lead_score >= 70 else "NEW"
        continued.summary = f"{channel.upper()} conversation update: {message[:1000]}"
        continued.updated_at = utcnow()
        db.add(
            AuditEvent(
                event_type="lead.updated_from_conversation",
                entity_type="lead",
                entity_id=str(continued.id),
                payload={"channel": channel, "score": continued.lead_score, "intent": intent, "event_id": event_id},
            )
        )
        db.commit()
        db.refresh(continued)
        return continued, False

    if intent == "general":
        score = 0

    lead = Lead(
        customer_id=customer.id,
        source_event_id=event_id,
        source_channel=channel,
        intent=intent,
        model_interest=model,
        budget_inr=budget,
        colour_preference=colour,
        transmission_preference=transmission,
        timeline_days=timeline_days,
        trade_in_vehicle=trade_in,
        lead_score=score,
        stage="QUALIFIED" if score >= 70 else ("UNQUALIFIED" if intent == "general" else "NEW"),
        summary=f"{channel.upper()} enquiry: {message[:1000]}",
        updated_at=utcnow(),
    )
    db.add(lead)
    db.flush()
    db.add(
        AuditEvent(
            event_type="lead.created",
            entity_type="lead",
            entity_id=str(lead.id),
            payload={"channel": channel, "score": score, "intent": intent, "event_id": event_id},
        )
    )
    db.commit()
    db.refresh(lead)
    return lead, True
