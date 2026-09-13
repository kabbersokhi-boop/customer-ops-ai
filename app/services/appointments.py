from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AuditEvent,
    BookingRecovery,
    Customer,
    Lead,
    ServiceBookingContext,
    ServiceRequest,
    ServiceSlot,
    SystemState,
    VehicleInventory,
)
from app.schemas.api import AppointmentCreate


class InventoryChanged(RuntimeError):
    pass


class ContactConflict(RuntimeError):
    pass


class SlotUnavailable(RuntimeError):
    pass


class SchedulerUnavailable(RuntimeError):
    def __init__(self, recovery: BookingRecovery) -> None:
        super().__init__("The scheduling provider did not respond")
        self.recovery = recovery


def _persist_confirmed_contact(db: Session, data: AppointmentCreate) -> None:
    if not any([data.contact_name, data.contact_phone, data.contact_email]):
        return
    lead = db.get(Lead, data.lead_id)
    if not lead:
        return
    customer = db.get(Customer, lead.customer_id)
    if not customer:
        return

    if data.contact_phone and data.contact_phone != customer.phone:
        existing = db.scalar(select(Customer).where(Customer.phone == data.contact_phone))
        if existing and existing.id != customer.id:
            raise ContactConflict("That phone number is already attached to another demo customer")
        customer.phone = data.contact_phone
    if data.contact_name:
        customer.name = data.contact_name
    if data.contact_email:
        customer.email = data.contact_email


def _scheduler_available(db: Session) -> bool:
    state = db.scalar(select(SystemState).where(SystemState.service_name == "scheduler"))
    return state is None or state.is_available


def _create_or_update_recovery(db: Session, data: AppointmentCreate) -> BookingRecovery:
    recovery = db.scalar(select(BookingRecovery).where(BookingRecovery.idempotency_key == data.idempotency_key))
    if recovery:
        recovery.attempts += 1
        recovery.last_error = "Scheduling provider timeout"
        recovery.status = "PENDING"
    else:
        recovery = BookingRecovery(
            idempotency_key=data.idempotency_key,
            lead_id=data.lead_id,
            service_request_id=data.service_request_id,
            slot_id=data.slot_id,
            requested_payload=data.model_dump(mode="json"),
            reason_code="SCHEDULER_TIMEOUT",
            last_error="Scheduling provider timeout",
        )
        db.add(recovery)
        db.flush()
    db.add(
        AuditEvent(
            event_type="appointment.recovery_created",
            entity_type="booking_recovery",
            entity_id=str(recovery.id),
            payload={
                "reason_code": recovery.reason_code,
                "service_request_id": data.service_request_id,
                "slot_id": data.slot_id,
                "duplicate_protection": True,
            },
        )
    )
    db.commit()
    db.refresh(recovery)
    return recovery


def _lock_service_slot(db: Session, data: AppointmentCreate) -> tuple[ServiceSlot, ServiceRequest]:
    if not data.slot_id or not data.service_request_id:
        raise SlotUnavailable("Service bookings require a verified slot and service request")
    slot = db.scalar(select(ServiceSlot).where(ServiceSlot.id == data.slot_id).with_for_update())
    request = db.get(ServiceRequest, data.service_request_id)
    if not slot or not request:
        raise SlotUnavailable("The selected service slot or request no longer exists")
    if slot.branch != data.branch or slot.starts_at != data.scheduled_for:
        raise SlotUnavailable("The selected service slot details changed; refresh availability")
    if not slot.is_active or slot.booked_count >= slot.capacity:
        raise SlotUnavailable("That service slot is no longer available; choose another verified slot")
    context = db.scalar(
        select(ServiceBookingContext).where(
            ServiceBookingContext.lead_id == data.lead_id,
            ServiceBookingContext.service_request_id == data.service_request_id,
            ServiceBookingContext.selected_slot_id == data.slot_id,
        )
    )
    if not context or context.status not in {"AWAITING_CONFIRMATION", "RECOVERY_PENDING"}:
        raise SlotUnavailable("The service booking has not reached explicit confirmation")
    return slot, request


def create_appointment(db: Session, data: AppointmentCreate):
    existing = db.scalar(select(Appointment).where(Appointment.idempotency_key == data.idempotency_key))
    if existing:
        return existing, False
    service_slot = None
    service_request = None
    if data.kind == "service":
        if not _scheduler_available(db):
            raise SchedulerUnavailable(_create_or_update_recovery(db, data))
        service_slot, service_request = _lock_service_slot(db, data)
    if data.stock_id:
        vehicle = db.scalar(select(VehicleInventory).where(VehicleInventory.stock_id == data.stock_id))
        if not vehicle or vehicle.status != "AVAILABLE":
            raise InventoryChanged("The selected vehicle is no longer available; refresh inventory before booking")

    _persist_confirmed_contact(db, data)
    appointment_fields = data.model_dump(
        exclude={"contact_name", "contact_phone", "contact_email", "service_request_id", "slot_id"}
    )
    appt = Appointment(**appointment_fields)
    db.add(appt)
    db.flush()
    if service_slot and service_request:
        service_slot.booked_count += 1
        service_request.stage = "BOOKED"
        context = db.scalar(
            select(ServiceBookingContext).where(ServiceBookingContext.service_request_id == service_request.id)
        )
        if context:
            context.status = "BOOKED"
    db.add(
        AuditEvent(
            event_type="appointment.booked",
            entity_type="appointment",
            entity_id=str(appt.id),
            payload={
                "lead_id": data.lead_id,
                "kind": data.kind,
                "stock_id": data.stock_id,
                "contact_confirmed": bool(data.contact_name and data.contact_phone and data.contact_email),
                "service_request_id": data.service_request_id,
                "slot_id": data.slot_id,
            },
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Appointment).where(Appointment.idempotency_key == data.idempotency_key))
        if existing:
            return existing, False
        raise
    db.refresh(appt)
    recovery = db.scalar(select(BookingRecovery).where(BookingRecovery.idempotency_key == data.idempotency_key))
    if recovery and recovery.status != "RESOLVED":
        recovery.status = "RESOLVED"
        recovery.resolved_appointment_id = appt.id
        recovery.last_error = None
        db.add(
            AuditEvent(
                event_type="appointment.recovery_resolved",
                entity_type="booking_recovery",
                entity_id=str(recovery.id),
                payload={"appointment_id": appt.id, "duplicate_created": False},
            )
        )
        db.commit()
    return appt, True


def recovery_payload(recovery: BookingRecovery) -> AppointmentCreate:
    return AppointmentCreate.model_validate(recovery.requested_payload)
