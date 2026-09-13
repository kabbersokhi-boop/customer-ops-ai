import os

os.environ["DATABASE_URL"] = "sqlite:///./test_inventory_recommendations.db"
os.environ["AIRTABLE_ENABLED"] = "false"
os.environ["NVIDIA_NIM_API_KEY"] = "replace_me"
os.environ["ORCHESTRATION_MODE"] = "direct"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import SystemState, VehicleInventory
from app.schemas.api import InventorySearch
from app.services.inventory import search_inventory


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add(SystemState(service_name="inventory", is_available=True))
        rows = [
            ("HYR-1", "Urban Cruiser Hyryder", "G NeoDrive", 1_750_000, False, 10),
            ("HYR-2", "Urban Cruiser Hyryder", "G NeoDrive", 1_720_000, True, 5),
            ("HYR-3", "Urban Cruiser Hyryder", "G NeoDrive", 1_710_000, False, 0),
            ("GLA-1", "Glanza", "V AMT", 1_050_000, True, 7),
            ("TAI-1", "Taisor", "V Turbo AT", 1_350_000, False, 3),
            ("RUM-1", "Rumion", "V AT", 1_350_000, False, 14),
        ]
        for stock_id, model, variant, price, test_drive, delivery in rows:
            db.add(
                VehicleInventory(
                    stock_id=stock_id,
                    model=model,
                    variant=variant,
                    fuel_type="Petrol",
                    transmission="Automatic",
                    colour="White",
                    branch="New Delhi",
                    demo_price_inr=price,
                    status="AVAILABLE",
                    test_drive_vehicle=test_drive,
                    expected_delivery_days=delivery,
                )
            )
        db.commit()
    finally:
        db.close()


def test_broad_discovery_surfaces_distinct_models_before_repeats():
    db = SessionLocal()
    try:
        rows = search_inventory(db, InventorySearch(max_budget_inr=2_000_000, transmission="Automatic"), limit=4)
        models = [row.model for row in rows]
        assert len(models) == 4
        assert len(set(models)) == 4
    finally:
        db.close()


def test_specific_model_search_can_return_multiple_stock_units():
    db = SessionLocal()
    try:
        rows = search_inventory(
            db,
            InventorySearch(model="Hyryder", max_budget_inr=2_000_000, transmission="Automatic"),
            limit=3,
        )
        assert len(rows) == 3
        assert all(row.model == "Urban Cruiser Hyryder" for row in rows)
        assert rows[0].stock_id == "HYR-2"
    finally:
        db.close()
