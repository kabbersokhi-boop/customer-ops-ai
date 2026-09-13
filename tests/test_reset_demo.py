from app.db.session import SessionLocal
from app.models import Customer, ServiceRequest, ServiceSlot
from app.services.ops import manager_briefing, operations_summary
from scripts.reset_demo import reset_database


def test_demo_reset_rebuilds_small_service_operations_baseline():
    reset_database()
    db = SessionLocal()
    try:
        assert db.query(Customer).count() == 8
        assert db.query(ServiceRequest).count() == 5
        assert db.query(ServiceSlot).count() == 6
        assert db.query(Customer).filter(Customer.name.like("Synthetic Eval%")).count() == 0
        summary = operations_summary(db)
        briefing = manager_briefing(db)
        assert summary["need_intervention"] == 3
        assert summary["human_handoffs"] == 1
        assert {"SAFETY_CASE", "HUMAN_HANDOFF", "APPROVAL"}.issubset(
            {item["type"] for item in briefing["attention"]}
        )
    finally:
        db.close()
