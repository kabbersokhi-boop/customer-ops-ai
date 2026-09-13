from app.db.session import SessionLocal
from app.models import Customer, ServiceRequest, ServiceSlot
from scripts.reset_demo import reset_database


def test_demo_reset_rebuilds_small_service_operations_baseline():
    reset_database()
    db = SessionLocal()
    try:
        assert db.query(Customer).count() == 8
        assert db.query(ServiceRequest).count() == 5
        assert db.query(ServiceSlot).count() == 6
        assert db.query(Customer).filter(Customer.name.like("Synthetic Eval%")).count() == 0
    finally:
        db.close()
