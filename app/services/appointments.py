from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Appointment, AuditEvent, VehicleInventory
from app.schemas.api import AppointmentCreate


class InventoryChanged(RuntimeError):
    pass


def create_appointment(db: Session, data: AppointmentCreate):
    existing = db.scalar(select(Appointment).where(Appointment.idempotency_key == data.idempotency_key))
    if existing:
        return existing, False
    if data.stock_id:
        vehicle = db.scalar(select(VehicleInventory).where(VehicleInventory.stock_id == data.stock_id))
        if not vehicle or vehicle.status != "AVAILABLE":
            raise InventoryChanged("The selected vehicle is no longer available; refresh inventory before booking")
    appt = Appointment(**data.model_dump())
    db.add(appt)
    db.flush()
    db.add(
        AuditEvent(
            event_type="appointment.booked",
            entity_type="appointment",
            entity_id=str(appt.id),
            payload={"lead_id": data.lead_id, "kind": data.kind, "stock_id": data.stock_id},
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Appointment).where(Appointment.idempotency_key == data.idempotency_key))
        return existing, False
    db.refresh(appt)
    return appt, True
