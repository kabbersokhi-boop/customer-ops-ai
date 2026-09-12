from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.db.session import engine, get_db
from app.models import (
    Appointment,
    ApprovalRequest,
    AuditEvent,
    CrmSync,
    Customer,
    Interaction,
    Lead,
    ServiceRequest,
    SystemState,
)
from app.schemas.api import (
    AppointmentCreate,
    ApprovalDecision,
    ChannelEvent,
    DiscountRequest,
    FailureToggle,
    InventorySearch,
    LeadIntake,
    LostLeadRecovery,
    ServiceIntake,
)
from app.services.agent import handle_channel_event
from app.services.appointments import InventoryChanged, create_appointment
from app.services.approvals import decide_approval, request_discount_approval
from app.services.crm import crm_provider_state, sync_appointment, sync_approval
from app.services.inventory import InventoryUnavailable, search_inventory
from app.services.leads import intake_lead
from app.services.ops import find_lost_leads, manager_briefing, operations_summary
from app.services.service_requests import create_service_request

Base.metadata.create_all(bind=engine)
app = FastAPI(
    title="AI Customer Operations Control Layer",
    version="0.2.0",
    description="Synthetic automotive AI transformation reference environment.",
)


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if settings.admin_api_key and x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail={"code": "ADMIN_AUTH_REQUIRED", "message": "Invalid admin key"})


def _inventory_row(row):
    return {
        "stock_id": row.stock_id,
        "model": row.model,
        "variant": row.variant,
        "fuel_type": row.fuel_type,
        "transmission": row.transmission,
        "colour": row.colour,
        "branch": row.branch,
        "demo_price_inr": row.demo_price_inr,
        "status": row.status,
        "test_drive_vehicle": row.test_drive_vehicle,
        "expected_delivery_days": row.expected_delivery_days,
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):
    states = {row.service_name: row.is_available for row in db.scalars(select(SystemState)).all()}
    return {
        "status": "ok",
        "environment": settings.app_env,
        "providers": {
            "database": "configured",
            "nvidia_nim": "configured"
            if settings.nvidia_nim_api_key and settings.nvidia_nim_api_key != "replace_me"
            else "mock/fallback",
            "airtable": crm_provider_state(),
        },
        "system_states": states,
    }


@app.get("/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(select(1)).scalar_one()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database readiness check failed"},
        ) from exc
    return {"status": "ready", "database": "reachable"}


@app.post("/api/channels/inbound")
async def channel_inbound(payload: ChannelEvent, db: Session = Depends(get_db)):
    return await handle_channel_event(db, payload)


@app.post("/api/inventory/search")
def inventory_search(payload: InventorySearch, db: Session = Depends(get_db)):
    try:
        rows = search_inventory(db, payload)
    except InventoryUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "DMS_UNAVAILABLE", "message": str(exc), "safe_fallback": True},
        ) from exc
    return [_inventory_row(row) for row in rows]


@app.post("/api/leads/intake")
def lead_intake(payload: LeadIntake, db: Session = Depends(get_db)):
    lead, created = intake_lead(db, payload.name, payload.phone, payload.message, payload.channel, payload.event_id)
    return {
        "lead_id": lead.id,
        "created": created,
        "lead_score": lead.lead_score,
        "stage": lead.stage,
        "intent": lead.intent,
        "model_interest": lead.model_interest,
        "budget_inr": lead.budget_inr,
        "colour": lead.colour_preference,
        "transmission": lead.transmission_preference,
        "timeline_days": lead.timeline_days,
        "trade_in": lead.trade_in_vehicle,
    }


@app.post("/api/service/intake")
def service_intake(payload: ServiceIntake, db: Session = Depends(get_db)):
    request, created = create_service_request(
        db,
        name=payload.name,
        phone=payload.phone,
        message=payload.message,
        vehicle_model=payload.vehicle_model,
        registration=payload.registration,
        preferred_time_text=payload.preferred_time_text,
        event_id=payload.event_id,
    )
    return {
        "service_request_id": request.id,
        "created": created,
        "urgency": request.urgency,
        "stage": request.stage,
    }


@app.post("/api/appointments")
async def appointment_create(payload: AppointmentCreate, db: Session = Depends(get_db)):
    lead = db.get(Lead, payload.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    try:
        appt, created = create_appointment(db, payload)
    except InventoryChanged as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "INVENTORY_CHANGED", "message": str(exc), "safe_fallback": True},
        ) from exc
    if created:
        lead.stage = "TEST_DRIVE_BOOKED" if payload.kind == "test_drive" else "APPOINTMENT_BOOKED"
        lead.updated_at = utcnow()
        db.add(lead)
        db.commit()
    crm = await sync_appointment(db, appt) if created else {"mode": "not_called", "status": "UNCHANGED"}
    return {
        "appointment_id": appt.id,
        "created": created,
        "status": appt.status,
        "idempotency": {"replayed": not created, "key": appt.idempotency_key},
        "crm": crm,
    }


@app.post("/api/approvals/discount")
async def approval_discount(
    payload: DiscountRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not db.get(Lead, payload.lead_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    result = request_discount_approval(db, payload.lead_id, payload.requested_discount_inr)
    if result.get("approval_required"):
        approval = db.get(ApprovalRequest, result["approval_id"])
        result["crm"] = await sync_approval(db, approval)
    return result


@app.get("/api/approvals")
def approvals_list(status: str | None = Query(default="PENDING"), db: Session = Depends(get_db)):
    stmt = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc()).limit(50)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status.upper())
    rows = db.scalars(stmt).all()
    return [
        {
            "id": row.id,
            "lead_id": row.lead_id,
            "action": row.action,
            "requested_value": row.requested_value,
            "recommendation": row.recommendation,
            "status": row.status,
            "decision_value": row.decision_value,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.post("/api/approvals/{approval_id}/decision")
async def approval_decision(
    approval_id: int,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    try:
        row = decide_approval(db, approval_id, payload.decision, payload.approved_value_inr, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")
    response = {
        "approval_id": row.id,
        "status": row.status,
        "decision_value": row.decision_value,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }
    response["crm"] = await sync_approval(db, row)
    return response


@app.post("/api/admin/failure")
def failure_toggle(
    payload: FailureToggle,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    state = db.scalar(select(SystemState).where(SystemState.service_name == payload.service_name))
    if not state:
        state = SystemState(service_name=payload.service_name, is_available=payload.is_available)
        db.add(state)
    else:
        state.is_available = payload.is_available
    db.add(
        AuditEvent(
            event_type="system.failure_toggle",
            entity_type="service",
            entity_id=payload.service_name,
            payload={"is_available": payload.is_available},
        )
    )
    db.commit()
    return {"service_name": payload.service_name, "is_available": payload.is_available}


@app.get("/api/ops/summary")
def ops_summary(db: Session = Depends(get_db)):
    return operations_summary(db)


@app.get("/api/ops/briefing")
def ops_briefing(db: Session = Depends(get_db)):
    return manager_briefing(db)


@app.get("/api/ops/lost-leads")
def ops_lost_leads(stale_hours: int = Query(default=24, ge=1, le=720), db: Session = Depends(get_db)):
    rows = find_lost_leads(db, stale_hours=stale_hours)
    return [
        {
            "id": row.id,
            "score": row.lead_score,
            "model_interest": row.model_interest,
            "stage": row.stage,
            "channel": row.source_channel,
            "updated_at": row.updated_at.isoformat(),
            "summary": row.summary,
        }
        for row in rows
    ]


@app.post("/api/ops/recover-lead")
def recover_lead(
    payload: LostLeadRecovery,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    lead = db.get(Lead, payload.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.stage == "REENGAGEMENT_QUEUED":
        return {"lead_id": lead.id, "stage": lead.stage, "idempotency": {"replayed": True}}
    previous_stage = lead.stage
    lead.stage = "REENGAGEMENT_QUEUED"
    lead.updated_at = utcnow()
    db.add(
        AuditEvent(
            event_type="lead.recovery_queued",
            entity_type="lead",
            entity_id=str(lead.id),
            payload={"previous_stage": previous_stage, "note": payload.note},
        )
    )
    db.commit()
    return {"lead_id": lead.id, "stage": lead.stage, "idempotency": {"replayed": False}}


@app.get("/api/ops/audit")
def ops_audit(limit: int = Query(default=30, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "payload": row.payload,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.get("/api/ops/interactions")
def ops_interactions(limit: int = Query(default=30, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.scalars(select(Interaction).order_by(Interaction.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "lead_id": row.lead_id,
            "channel": row.channel,
            "direction": row.direction,
            "content": row.content,
            "intent": row.intent,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.get("/api/ops/leads")
def ops_leads(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.scalars(select(Lead).order_by(Lead.updated_at.desc()).limit(limit)).all()
    customer_ids = {row.customer_id for row in rows}
    customers = {row.id: row for row in db.scalars(select(Customer).where(Customer.id.in_(customer_ids))).all()}
    return [
        {
            "id": row.id,
            "customer_name": customers[row.customer_id].name,
            "channel": row.source_channel,
            "intent": row.intent,
            "score": row.lead_score,
            "stage": row.stage,
            "model_interest": row.model_interest,
            "budget_inr": row.budget_inr,
            "colour": row.colour_preference,
            "transmission": row.transmission_preference,
            "timeline_days": row.timeline_days,
            "trade_in": row.trade_in_vehicle,
            "crm_sync_status": row.crm_sync_status,
            "crm_record_id": row.crm_record_id,
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


@app.get("/api/ops/appointments")
def ops_appointments(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.scalars(select(Appointment).order_by(Appointment.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "lead_id": row.lead_id,
            "kind": row.kind,
            "branch": row.branch,
            "stock_id": row.stock_id,
            "scheduled_for": row.scheduled_for.isoformat(),
            "status": row.status,
            "idempotency_key": row.idempotency_key,
        }
        for row in rows
    ]


@app.get("/api/ops/service-requests")
def ops_service_requests(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.scalars(select(ServiceRequest).order_by(ServiceRequest.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "vehicle_model": row.vehicle_model,
            "issue_summary": row.issue_summary,
            "urgency": row.urgency,
            "stage": row.stage,
            "preferred_time_text": row.preferred_time_text,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.get("/api/ops/crm-sync")
def ops_crm_sync(limit: int = Query(default=30, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.scalars(select(CrmSync).order_by(CrmSync.updated_at.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "provider": row.provider,
            "status": row.status,
            "record_id": row.record_id,
            "record_url": row.record_url,
            "operation": row.operation,
            "attempts": row.attempts,
            "last_error_code": row.last_error_code,
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


@app.get("/", include_in_schema=False)
def demo_ui():
    return FileResponse("app/static/index.html")
