from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import (
    Appointment,
    ApprovalRequest,
    AuditEvent,
    BookingRecovery,
    CrmSync,
    Customer,
    Interaction,
    Lead,
    ServiceBookingContext,
    ServiceRequest,
    SystemState,
)
from app.services.service_scheduling import demo_today

NOISE_CHANNELS = {"adversarial-demo-eval", "browser-demo-eval", "airtable-eval", "probe"}


def _operator_leads():
    return select(Lead).where(~Lead.source_channel.in_(NOISE_CHANNELS))


def operations_summary(db: Session) -> dict:
    now = utcnow()
    day_start = datetime.combine(demo_today(), time.min)
    day_end = day_start + timedelta(days=1)
    service_today = db.scalar(
        select(func.count()).select_from(Appointment).where(
            Appointment.kind == "service",
            Appointment.scheduled_for >= day_start,
            Appointment.scheduled_for < day_end,
            Appointment.status.in_(["BOOKED", "COMPLETED"]),
        )
    ) or 0
    pending_recovery = db.scalar(
        select(func.count()).select_from(BookingRecovery).where(BookingRecovery.status.in_(["PENDING", "NEEDS_REVIEW"]))
    ) or 0
    urgent_open = db.scalar(
        select(func.count()).select_from(ServiceRequest).where(
            ServiceRequest.urgency.in_(["HIGH", "CRITICAL"]),
            ServiceRequest.stage.in_(["OPEN", "NEEDS_ADVISOR"]),
        )
    ) or 0
    pending_confirmation = db.scalar(
        select(func.count()).select_from(ServiceBookingContext).where(
            ServiceBookingContext.status.in_(["AWAITING_CONFIRMATION", "ALTERNATIVES_OFFERED", "AWAITING_SLOT_SELECTION"])
        )
    ) or 0
    pending_approvals = db.scalar(
        select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.status == "PENDING")
    ) or 0
    human_handoffs = db.scalar(
        select(func.count()).select_from(_operator_leads().where(Lead.stage == "HUMAN_HANDOFF_REQUESTED").subquery())
    ) or 0
    crm_failures = db.scalar(select(func.count()).select_from(CrmSync).where(CrmSync.status == "FAILED")) or 0
    service_bookings = db.scalar(
        select(func.count()).select_from(Appointment).where(Appointment.kind == "service")
    ) or 0
    service_requests = db.scalar(select(func.count()).select_from(ServiceRequest)) or 0
    automatically_resolved = min(service_bookings, service_requests)
    automation_rate = round((automatically_resolved / service_requests) * 100) if service_requests else 0
    sla_at_risk = db.scalar(
        select(func.count()).select_from(ServiceRequest).where(
            ServiceRequest.urgency.in_(["HIGH", "CRITICAL"]),
            ServiceRequest.stage.in_(["OPEN", "NEEDS_ADVISOR"]),
            ServiceRequest.created_at < now - timedelta(minutes=15),
        )
    ) or 0
    needs_intervention = urgent_open + pending_recovery + crm_failures + pending_approvals + human_handoffs
    return {
        "bookings_today": service_today,
        "need_intervention": needs_intervention,
        "awaiting_confirmation": pending_confirmation,
        "automation_rate": automation_rate,
        "automatically_resolved": automatically_resolved,
        "sla_at_risk": sla_at_risk,
        "safety_sensitive": urgent_open,
        "integration_issues": pending_recovery + crm_failures,
        "pending_recoveries": pending_recovery,
        "pending_approvals": pending_approvals,
        "human_handoffs": human_handoffs,
        "appointments": db.scalar(select(func.count()).select_from(Appointment)) or 0,
        "service_requests": service_requests,
        "leads": db.scalar(select(func.count()).select_from(_operator_leads().subquery())) or 0,
        "hot_leads": db.scalar(select(func.count()).select_from(_operator_leads().where(Lead.lead_score >= 80).subquery())) or 0,
        "interactions_24h": db.scalar(
            select(func.count()).select_from(Interaction).where(
                Interaction.created_at >= now - timedelta(hours=24), ~Interaction.channel.in_(NOISE_CHANNELS)
            )
        )
        or 0,
        "audit_events": db.scalar(select(func.count()).select_from(AuditEvent)) or 0,
        "crm_sync_failures": crm_failures,
        "definitions": {
            "bookings_today": "Confirmed service appointments scheduled for today in the demo timezone.",
            "need_intervention": (
                "Open safety cases, booking recoveries, CRM failures, human handoffs, and pending approvals."
            ),
            "automation_rate": "Confirmed service bookings divided by service requests in stored demo state.",
            "sla_at_risk": "High or critical service cases open for more than 15 minutes.",
            "integration_issues": "Pending booking recoveries plus failed CRM projections.",
        },
    }


def find_lost_leads(db: Session, stale_hours: int = 24, limit: int = 20) -> list[Lead]:
    cutoff = utcnow() - timedelta(hours=stale_hours)
    booked_lead_ids = select(Appointment.lead_id).where(Appointment.status.in_(["BOOKED", "COMPLETED"]))
    stmt = (
        _operator_leads()
        .where(
            Lead.lead_score >= 70,
            Lead.stage.in_(["QUALIFIED", "NEW"]),
            Lead.updated_at < cutoff,
            ~Lead.id.in_(booked_lead_ids),
        )
        .order_by(Lead.lead_score.desc(), Lead.updated_at.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def manager_briefing(db: Session) -> dict:
    metrics = operations_summary(db)
    attention: list[dict] = []

    down = [state.service_name for state in db.scalars(select(SystemState)).all() if not state.is_available]
    for service in down:
        attention.append(
            {
                "type": "SYSTEM_STATE",
                "severity": "critical",
                "title": f"{service.title()} unavailable",
                "detail": "Safe fallback is active; consequential actions will not report false success.",
                "action": "View technical trace",
                "entity_id": service,
            }
        )

    recoveries = db.execute(
        select(BookingRecovery, Lead, Customer)
        .join(Lead, Lead.id == BookingRecovery.lead_id)
        .join(Customer, Customer.id == Lead.customer_id)
        .where(BookingRecovery.status.in_(["PENDING", "NEEDS_REVIEW"]))
        .order_by(BookingRecovery.created_at)
        .limit(5)
    ).all()
    for recovery, _, customer in recoveries:
        payload = recovery.requested_payload
        attention.append(
            {
                "type": "BOOKING_RECOVERY",
                "severity": "high",
                "title": f"{customer.name} — booking confirmation required",
                "detail": (
                    f"{payload.get('branch')} · {payload.get('scheduled_for')} · scheduling timeout · "
                    "details preserved · duplicate protection active"
                ),
                "action": "Retry booking",
                "entity_id": recovery.id,
            }
        )

    for sync in db.scalars(
        select(CrmSync).where(CrmSync.status == "FAILED").order_by(CrmSync.updated_at).limit(5)
    ).all():
        attention.append(
            {
                "type": "CRM_SYNC",
                "severity": "medium",
                "title": "CRM sync delayed",
                "detail": f"{sync.entity_type} {sync.entity_id} is safe in PostgreSQL · retry pending",
                "action": "View technical trace",
                "entity_id": sync.id,
            }
        )

    urgent = db.execute(
        select(ServiceRequest, Customer)
        .join(Customer, Customer.id == ServiceRequest.customer_id)
        .where(
            ServiceRequest.urgency.in_(["HIGH", "CRITICAL"]),
            ServiceRequest.stage.in_(["OPEN", "NEEDS_ADVISOR"]),
        )
        .order_by(ServiceRequest.created_at)
        .limit(5)
    ).all()
    for request, customer in urgent:
        waited = max(0, int((utcnow() - request.created_at).total_seconds() // 60))
        attention.append(
            {
                "type": "SAFETY_CASE",
                "severity": "critical" if request.urgency == "CRITICAL" else "high",
                "title": f"{customer.name} — {request.issue_summary[:60]}",
                "detail": f"Safety-sensitive · no advisor assigned · waiting {waited} min",
                "action": "Review case",
                "entity_id": request.id,
            }
        )

    handoffs = db.execute(
        _operator_leads()
        .join(Customer, Customer.id == Lead.customer_id)
        .where(Lead.stage == "HUMAN_HANDOFF_REQUESTED")
        .order_by(Lead.updated_at)
        .limit(5)
        .with_only_columns(Lead, Customer)
    ).all()
    for lead, customer in handoffs:
        attention.append(
            {
                "type": "HUMAN_HANDOFF",
                "severity": "medium",
                "title": f"{customer.name} — advisor requested",
                "detail": lead.summary or "Customer asked for a human advisor.",
                "action": "View customer context",
                "entity_id": lead.id,
            }
        )

    approvals = db.execute(
        select(ApprovalRequest, Lead, Customer)
        .join(Lead, Lead.id == ApprovalRequest.lead_id)
        .join(Customer, Customer.id == Lead.customer_id)
        .where(ApprovalRequest.status == "PENDING")
        .order_by(ApprovalRequest.created_at)
        .limit(5)
    ).all()
    for approval, lead, customer in approvals:
        attention.append(
            {
                "type": "APPROVAL",
                "severity": "medium",
                "title": f"{customer.name} — commercial decision required",
                "detail": approval.recommendation or f"{lead.intent.title()} request requires manager review.",
                "action": "Review decision",
                "entity_id": approval.id,
            }
        )
    if not attention:
        attention.append(
            {
                "type": "CLEAR",
                "severity": "info",
                "title": "No operational exceptions need attention",
                "detail": "Service bookings, safety work, and integration state are within the demo thresholds.",
                "action": "Monitor",
                "entity_id": None,
            }
        )
    return {
        "generated_at": utcnow().isoformat() + "Z",
        "metrics": metrics,
        "attention": attention[:8],
        "grounding": "Generated only from stored demo operational data; no live dealer data is used.",
    }
