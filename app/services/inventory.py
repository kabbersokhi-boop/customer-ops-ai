from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SystemState, VehicleInventory
from app.schemas.api import InventorySearch


class InventoryUnavailable(RuntimeError):
    pass


def _assert_available(db: Session):
    state = db.scalar(select(SystemState).where(SystemState.service_name == "inventory"))
    if state and not state.is_available:
        raise InventoryUnavailable("Inventory/DMS service is unavailable")


def search_inventory(db: Session, query: InventorySearch):
    _assert_available(db)
    stmt = select(VehicleInventory).where(VehicleInventory.status == "AVAILABLE")
    if query.model:
        stmt = stmt.where(VehicleInventory.model.ilike(f"%{query.model}%"))
    if query.max_budget_inr:
        stmt = stmt.where(VehicleInventory.demo_price_inr <= query.max_budget_inr)
    if query.transmission:
        stmt = stmt.where(VehicleInventory.transmission.ilike(f"%{query.transmission}%"))
    if query.colour:
        stmt = stmt.where(VehicleInventory.colour.ilike(f"%{query.colour}%"))
    if query.branch:
        stmt = stmt.where(VehicleInventory.branch.ilike(f"%{query.branch}%"))
    return list(db.scalars(stmt.limit(20)).all())
