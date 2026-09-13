from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import Appointment, ApprovalRequest, AuditEvent, CrmSync, Customer, Interaction, Lead, SystemState
from app.providers.airtable import AirtableCRM, AirtableProviderError, AirtableRecord


def _crm_available(db: Session) -> bool:
    state = db.scalar(select(SystemState).where(SystemState.service_name == "crm"))
    return state is None or state.is_available


def _sync_row(db: Session, entity_type: str, entity_id: str) -> CrmSync:
    row = db.scalar(
        select(CrmSync).where(
            CrmSync.entity_type == entity_type,
            CrmSync.entity_id == entity_id,
            CrmSync.provider == "airtable",
        )
    )
    if row:
        row.attempts += 1
        return row
    row = CrmSync(entity_type=entity_type, entity_id=entity_id, provider="airtable", status="PENDING")
    db.add(row)
    return row


async def _run_sync(
    db: Session,
    entity_type: str,
    entity_id: str,
    operation: Callable[[], Awaitable[AirtableRecord]],
) -> dict:
    row = _sync_row(db, entity_type, entity_id)
    if not _crm_available(db):
        row.status = "FAILED"
        row.last_error_code = "CRM_UNAVAILABLE"
        row.updated_at = utcnow()
        db.add(
            AuditEvent(
                event_type="crm.sync_failed",
                entity_type=entity_type,
                entity_id=entity_id,
                payload={"provider": "airtable", "code": "CRM_UNAVAILABLE", "retryable": True},
            )
        )
        db.commit()
        return {"mode": "failed", "status": row.status, "error_code": row.last_error_code}

    try:
        result = await operation()
        row.status = "MOCK" if result.mode == "mock" else "SYNCED"
        row.record_id = result.record_id
        row.record_url = result.record_url
        row.operation = result.operation
        row.last_error_code = None
        row.updated_at = utcnow()
        db.commit()
        return {
            "mode": result.mode,
            "status": row.status,
            "record_id": result.record_id,
            "record_url": result.record_url,
            "operation": result.operation,
        }
    except AirtableProviderError as exc:
        row.status = "FAILED"
        row.last_error_code = exc.code
        row.updated_at = utcnow()
        db.add(
            AuditEvent(
                event_type="crm.sync_failed",
                entity_type=entity_type,
                entity_id=entity_id,
                payload={"provider": "airtable", "code": exc.code, "retryable": exc.retryable},
            )
        )
        db.commit()
        return {"mode": "failed", "status": row.status, "error_code": exc.code, "retryable": exc.retryable}


async def sync_customer(db: Session, customer: Customer) -> dict:
    fields = {
        "Customer ID": str(customer.id),
        "Name": customer.name,
        "Phone": customer.phone,
        "Email": customer.email or "",
        "Created At": customer.created_at.isoformat(),
    }
    crm = AirtableCRM()
    return await _run_sync(db, "customer", str(customer.id), lambda: crm.sync_customer(fields))


async def sync_lead(db: Session, lead: Lead) -> dict:
    fields = {
        "Lead ID": str(lead.id),
        "Customer ID": str(lead.customer_id),
        "Channel": lead.source_channel,
        "Intent": lead.intent,
        "Model Interest": lead.model_interest or "",
        "Budget INR": lead.budget_inr or 0,
        "Colour": lead.colour_preference or "",
        "Transmission": lead.transmission_preference or "",
        "Timeline Days": lead.timeline_days if lead.timeline_days is not None else 0,
        "Trade In": lead.trade_in_vehicle or "",
        "Lead Score": lead.lead_score,
        "Stage": lead.stage,
        "Summary": lead.summary[:1000],
    }
    crm = AirtableCRM()
    result = await _run_sync(db, "lead", str(lead.id), lambda: crm.sync_lead(fields))
    lead.crm_record_id = result.get("record_id")
    lead.crm_sync_status = result["status"]
    db.commit()
    return result


async def sync_activity(db: Session, activity: Interaction) -> dict:
    fields = {
        "Activity ID": str(activity.id),
        "Lead ID": str(activity.lead_id or ""),
        "Direction": activity.direction,
        "Channel": activity.channel,
        "Intent": activity.intent or "",
        "Content": activity.content[:2000],
        "Created At": activity.created_at.isoformat(),
    }
    crm = AirtableCRM()
    return await _run_sync(db, "activity", str(activity.id), lambda: crm.sync_activity(fields))


async def sync_appointment(db: Session, appointment: Appointment) -> dict:
    # Contact details can be confirmed at booking time. The appointment service
    # persists those changes to PostgreSQL first; refresh the related customer
    # projection before syncing the appointment so Airtable cannot stay stale.
    lead = db.get(Lead, appointment.lead_id)
    if lead:
        customer = db.get(Customer, lead.customer_id)
        if customer:
            await sync_customer(db, customer)

    fields = {
        "Appointment ID": str(appointment.id),
        "Lead ID": str(appointment.lead_id),
        "Kind": appointment.kind,
        "Branch": appointment.branch,
        "Stock ID": appointment.stock_id or "",
        "Scheduled For": appointment.scheduled_for.isoformat(),
        "Status": appointment.status,
        "Idempotency Key": appointment.idempotency_key,
    }
    crm = AirtableCRM()
    return await _run_sync(
        db,
        "appointment",
        str(appointment.id),
        lambda: crm.sync_appointment(fields),
    )


async def sync_approval(db: Session, approval: ApprovalRequest) -> dict:
    fields = {
        "Approval ID": str(approval.id),
        "Lead ID": str(approval.lead_id),
        "Action": approval.action,
        "Requested Value": approval.requested_value,
        "Recommendation": approval.recommendation,
        "Status": approval.status,
        "Decision Value": approval.decision_value or "",
        "Created At": approval.created_at.isoformat(),
    }
    crm = AirtableCRM()
    return await _run_sync(db, "approval", str(approval.id), lambda: crm.sync_approval(fields))


def crm_provider_state() -> str:
    return "enabled" if AirtableCRM().enabled else "mock/disabled"
