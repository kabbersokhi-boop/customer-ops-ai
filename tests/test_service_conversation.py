from unittest.mock import AsyncMock, patch

import uvloop
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models import CustomerProfile, ServiceRequest
from app.schemas.api import ChannelEvent
from app.services.agent import handle_channel_event
from app.services.service_scheduling import next_weekday, seed_service_slots


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    seed_service_slots(db)
    db.commit()
    return db


def _event(event_id: str, text: str, *, lead_id: int | None = None) -> ChannelEvent:
    return ChannelEvent(
        event_id=event_id,
        channel="demo-messaging",
        customer_name="Arjun Mehta",
        customer_phone="synthetic-123456",
        text=text,
        conversation_lead_id=lead_id,
        metadata={"demo_ui": True, "vehicle_model": "Innova Hycross"},
    )


def _run(db, event: ChannelEvent):
    lead_sync = AsyncMock(return_value={"mode": "mock", "status": "MOCK", "record_id": None, "record_url": None})
    customer_sync = AsyncMock(return_value={"mode": "mock", "status": "MOCK", "record_id": None, "record_url": None})
    activity_sync = AsyncMock(return_value={"mode": "mock", "status": "MOCK"})
    with (
        patch("app.services.agent.sync_lead", lead_sync),
        patch("app.services.agent.sync_customer", customer_sync),
        patch("app.services.agent.sync_activity", activity_sync),
    ):
        return uvloop.run(handle_channel_event(db, event))


def test_multi_day_request_respects_customer_preference_order():
    db = _session()
    try:
        body = _run(
            db,
            _event(
                "service-preference-order",
                "My Innova is due for its 40,000 km service. Saturday would be easiest but I can do Monday if needed.",
            ),
        )
        booking = body["service_booking"]
        assert booking["status"] == "ALTERNATIVES_OFFERED"
        assert booking["requested"]["date"] == next_weekday("saturday").isoformat()
        assert booking["alternatives"][0]["label"].startswith("Monday")
    finally:
        db.close()


def test_active_service_context_rejects_unrelated_questions_without_replaying_slots():
    db = _session()
    try:
        first = _run(db, _event("service-scope-start", "My car needs its 40,000 km service. Can I come Saturday?"))
        second = _run(
            db,
            _event(
                "service-scope-unrelated",
                "What is the capital of France?",
                lead_id=first["lead"]["id"],
            ),
        )
        assert second["conversation"]["request_type"] == "service_out_of_scope"
        assert second["service_booking"] is None
        assert second["response_mode"] == "deterministic-service-scope-boundary"
        assert "focused on vehicle service" in second["reply"].lower()
    finally:
        db.close()


def test_active_service_context_accepts_real_scheduling_followup():
    db = _session()
    try:
        first = _run(db, _event("service-followup-start", "My car needs its 40,000 km service. Can I come Saturday?"))
        second = _run(
            db,
            _event("service-followup-monday", "Actually Monday works.", lead_id=first["lead"]["id"]),
        )
        assert second["conversation"]["request_type"] == "service_request"
        assert second["service_booking"]["status"] == "AWAITING_SLOT_SELECTION"
        assert second["service_booking"]["available"]
        assert all(item["label"].startswith("Monday") for item in second["service_booking"]["available"])
    finally:
        db.close()


def test_service_language_reasoning_uses_nim_only_for_bounded_day_interpretation(monkeypatch):
    db = _session()
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-only")
    provider_call = AsyncMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": '{"primary_day":"saturday","fallback_day":"monday"}'
                    }
                }
            ]
        }
    )
    try:
        with patch("app.services.agent.NIMClient.chat", provider_call):
            body = _run(
                db,
                _event(
                    "service-nim-bounded",
                    "My Innova is due for its 40,000 km service. Saturday is best, but Monday is my backup.",
                ),
            )
        assert body["response_mode"] == "governed-service-nim"
        assert body["provider"]["status"] == "ok"
        assert body["provider"]["purpose"] == "service_language_interpretation"
        assert body["provider"]["interpreted"] == {"primary_day": "saturday", "fallback_day": "monday"}
        assert body["service_booking"]["requested"]["date"] == next_weekday("saturday").isoformat()
    finally:
        db.close()


def test_onboarding_vehicle_is_persisted_into_service_customer_context():
    db = _session()
    try:
        body = _run(db, _event("service-vehicle-context", "My car needs its 40,000 km service. Can I come Saturday?"))
        request = db.get(ServiceRequest, body["service_request_id"])
        profile = db.scalar(select(CustomerProfile).where(CustomerProfile.customer_id == request.customer_id))
        assert request.vehicle_model == "Innova Hycross"
        assert profile is not None
        assert profile.vehicle_model == "Innova Hycross"
    finally:
        db.close()
