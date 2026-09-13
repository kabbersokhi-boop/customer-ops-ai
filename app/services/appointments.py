from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Appointment, AuditEvent, Customer, Lead, VehicleInventory
from app.schemas.api import AppointmentCreate


class InventoryChanged(RuntimeError):
    pass


class ContactConflict(RuntimeError):
    pass


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


def create_appointment(db: Session, data: AppointmentCreate):
    existing = db.scalar(select(Appointment).where(Appointment.idempotency_key == data.idempotency_key))
    if existing:
        return existing, False
    if data.stock_id:
        vehicle = db.scalar(select(VehicleInventory).where(VehicleInventory.stock_id == data.stock_id))
        if not vehicle or vehicle.status != "AVAILABLE":
            raise InventoryChanged("The selected vehicle is no longer available; refresh inventory before booking")

    _persist_confirmed_contact(db, data)
    appointment_fields = data.model_dump(exclude={"contact_name", "contact_phone", "contact_email"})
    appt = Appointment(**appointment_fields)
    db.add(appt)
    db.flush()
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
    return appt, True
