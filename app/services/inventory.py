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


def _rank_inventory(rows: list[VehicleInventory], query: InventorySearch) -> list[VehicleInventory]:
    """Rank verified rows and diversify broad discovery searches by model.

    A specific model search should show the best matching stock units for that model.
    A broad search should first surface one strong candidate per model before showing
    additional units from the same model, so the customer sees actual choice rather
    than three near-identical rows that only reflect insertion order.
    """

    ranked = sorted(
        rows,
        key=lambda vehicle: (
            0 if vehicle.test_drive_vehicle else 1,
            vehicle.expected_delivery_days,
            vehicle.demo_price_inr,
            vehicle.model,
            vehicle.variant,
            vehicle.stock_id,
        ),
    )

    if query.model:
        return ranked

    diverse: list[VehicleInventory] = []
    repeats: list[VehicleInventory] = []
    seen_models: set[str] = set()
    for vehicle in ranked:
        if vehicle.model not in seen_models:
            diverse.append(vehicle)
            seen_models.add(vehicle.model)
        else:
            repeats.append(vehicle)
    return diverse + repeats


def search_inventory(db: Session, query: InventorySearch, limit: int = 20):
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

    # Broad discovery needs a wider candidate pool; otherwise insertion order can
    # fill the first 20 rows with one model before another valid model is considered.
    candidate_limit = max(limit, 200) if not query.model else max(limit, 20)
    rows = list(db.scalars(stmt.limit(candidate_limit)).all())
    return _rank_inventory(rows, query)[:limit]
