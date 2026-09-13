from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import (
    Appointment,
    ApprovalRequest,
    AuditEvent,
    CrmSync,
    Customer,
    CustomerProfile,
    Interaction,
    Lead,
    ServiceBookingContext,
    ServiceRequest,
    SystemState,
)
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
    profile = db.scalar(select(CustomerProfile).where(CustomerProfile.customer_id == customer.id))
    last_interaction = db.scalar(
        select(Interaction).where(Interaction.customer_id == customer.id).order_by(Interaction.created_at.desc()).limit(1)
    )
    fields = {
        "Customer ID": str(customer.id),
        "Name": customer.name,
        "Phone": customer.phone,
        "Email": customer.email or "",
        "Created At": customer.created_at.isoformat(),
        "Vehicle": profile.vehicle_model if profile and profile.vehicle_model else "",
        "Registration": profile.registration if profile and profile.registration else "",
        "Preferred Branch": profile.preferred_branch if profile else "",
        "Last Interaction": last_interaction.created_at.isoformat() if last_interaction else "",
        "Current Status": profile.current_status if profile else "ACTIVE",
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
    customer = None
    profile = None
    service_request = None
    if lead:
        customer = db.get(Customer, lead.customer_id)
        if customer:
            await sync_customer(db, customer)
            profile = db.scalar(select(CustomerProfile).where(CustomerProfile.customer_id == customer.id))
    if appointment.kind == "service":
        context = db.scalar(select(ServiceBookingContext).where(ServiceBookingContext.lead_id == appointment.lead_id))
        if context:
            service_request = db.get(ServiceRequest, context.service_request_id)

    fields = {
        "Appointment ID": str(appointment.id),
        "Lead ID": str(appointment.lead_id),
        "Kind": appointment.kind,
        "Branch": appointment.branch,
        "Stock ID": appointment.stock_id or "",
        "Scheduled For": appointment.scheduled_for.isoformat(),
        "Status": appointment.status,
        "Idempotency Key": appointment.idempotency_key,
        "Customer": customer.name if customer else "",
        "Vehicle": (
            service_request.vehicle_model
            if service_request and service_request.vehicle_model
            else profile.vehicle_model
            if profile and profile.vehicle_model
            else ""
        ),
        "Service Request": service_request.issue_summary[:500] if service_request else "",
        "Assigned Advisor": "Unassigned",
        "Attendance": "Scheduled",
        "CRM Update State": "Synchronized",
        "Next Action": "Prepare service reception" if appointment.kind == "service" else "Confirm test drive",
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
