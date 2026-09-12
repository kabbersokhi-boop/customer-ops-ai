from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import Appointment, ApprovalRequest, AuditEvent, CrmSync, Interaction, Lead, ServiceRequest, SystemState


def operations_summary(db: Session) -> dict:
    now = utcnow()
    last_24h = now - timedelta(hours=24)
    return {
        "leads": db.scalar(select(func.count()).select_from(Lead)) or 0,
        "hot_leads": db.scalar(select(func.count()).select_from(Lead).where(Lead.lead_score >= 80)) or 0,
        "appointments": db.scalar(select(func.count()).select_from(Appointment)) or 0,
        "service_requests": db.scalar(select(func.count()).select_from(ServiceRequest)) or 0,
        "pending_approvals": db.scalar(
            select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.status == "PENDING")
        )
        or 0,
        "interactions_24h": db.scalar(
            select(func.count()).select_from(Interaction).where(Interaction.created_at >= last_24h)
        )
        or 0,
        "audit_events": db.scalar(select(func.count()).select_from(AuditEvent)) or 0,
        "crm_sync_failures": db.scalar(select(func.count()).select_from(CrmSync).where(CrmSync.status == "FAILED"))
        or 0,
    }


def find_lost_leads(db: Session, stale_hours: int = 24, limit: int = 20) -> list[Lead]:
    cutoff = utcnow() - timedelta(hours=stale_hours)
    booked_lead_ids = select(Appointment.lead_id).where(Appointment.status.in_(["BOOKED", "COMPLETED"]))
    stmt = (
        select(Lead)
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
    lost = find_lost_leads(db, stale_hours=24, limit=5)
    high_urgency_service = list(
        db.scalars(
            select(ServiceRequest)
            .where(ServiceRequest.urgency.in_(["HIGH", "CRITICAL"]), ServiceRequest.stage == "OPEN")
            .order_by(ServiceRequest.created_at.asc())
            .limit(5)
        ).all()
    )
    approvals = list(
        db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.status == "PENDING")
            .order_by(ApprovalRequest.created_at.asc())
            .limit(5)
        ).all()
    )
    system_states = list(db.scalars(select(SystemState)).all())

    attention: list[dict] = []
    if lost:
        attention.append(
            {
                "severity": "high",
                "title": f"{len(lost)} high-intent leads need recovery",
                "detail": "Qualified leads have no booking and no recent activity.",
                "entity_ids": [lead.id for lead in lost],
            }
        )
    if approvals:
        attention.append(
            {
                "severity": "medium",
                "title": f"{len(approvals)} commercial approvals are waiting",
                "detail": "AI has paused consequential discount actions for human review.",
                "entity_ids": [item.id for item in approvals],
            }
        )
    if high_urgency_service:
        attention.append(
            {
                "severity": "high",
                "title": f"{len(high_urgency_service)} urgent service cases are open",
                "detail": "Prioritize safety-related customer issues before routine service work.",
                "entity_ids": [item.id for item in high_urgency_service],
            }
        )
    down = [state.service_name for state in system_states if not state.is_available]
    if down:
        attention.append(
            {
                "severity": "critical",
                "title": "Upstream systems unavailable",
                "detail": f"Safe fallback active for: {', '.join(down)}.",
                "entity_ids": down,
            }
        )
    if metrics["crm_sync_failures"]:
        attention.append(
            {
                "severity": "medium",
                "title": f"{metrics['crm_sync_failures']} CRM sync operations need retry",
                "detail": "Operational state is preserved locally; provider repair can replay idempotent upserts.",
                "entity_ids": [],
            }
        )
    if not attention:
        attention.append(
            {
                "severity": "info",
                "title": "No critical exceptions detected",
                "detail": "Continue monitoring high-intent leads, appointments, and service demand.",
                "entity_ids": [],
            }
        )

    return {
        "generated_at": utcnow().isoformat() + "Z",
        "metrics": metrics,
        "attention": attention,
        "grounding": "Generated only from stored demo operational data; no live dealer data is used.",
    }
