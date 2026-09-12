import asyncio
import os
from datetime import timedelta
from unittest.mock import AsyncMock, patch

os.environ["DATABASE_URL"] = "sqlite:///./test_customer_ops.db"
os.environ["AIRTABLE_ENABLED"] = "false"
os.environ["NVIDIA_NIM_API_KEY"] = ""

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Appointment, Interaction, Lead, ServiceRequest, SystemState, VehicleInventory
from app.providers.nim import NIMProviderError


class APIClient:
    def request(self, method: str, path: str, **kwargs):
        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as session:
                return await session.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)


client = APIClient()


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add(SystemState(service_name="inventory", is_available=True))
        db.add(
            VehicleInventory(
                stock_id="TEST-FOR-0001",
                model="Fortuner",
                variant="4x2 AT",
                fuel_type="Diesel",
                transmission="Automatic",
                colour="Pearl White",
                branch="Gurugram",
                demo_price_inr=4_200_000,
                status="AVAILABLE",
                test_drive_vehicle=True,
                expected_delivery_days=3,
            )
        )
        db.commit()
    finally:
        db.close()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_lead_intake_extracts_business_context():
    response = client.post(
        "/api/leads/intake",
        json={
            "name": "Demo Customer",
            "phone": "+919999900001",
            "message": "I want to buy a white Fortuner automatic under 45 lakh this month and book a test drive. I have a Creta to exchange.",
            "channel": "whatsapp-demo",
            "event_id": "evt-lead-001",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model_interest"] == "Fortuner"
    assert body["budget_inr"] == 4_500_000
    assert body["transmission"] == "Automatic"
    assert body["timeline_days"] == 30
    assert body["lead_score"] >= 80


def test_saturday_does_not_false_positive_as_automatic_transmission():
    response = client.post(
        "/api/leads/intake",
        json={
            "name": "Manual Customer",
            "phone": "+919999900099",
            "message": "I want a Fortuner manual test drive on Saturday.",
            "event_id": "evt-manual-saturday",
        },
    )
    assert response.status_code == 200
    assert response.json()["transmission"] == "Manual"


def test_duplicate_webhook_does_not_duplicate_lead():
    payload = {
        "name": "Idempotent Customer",
        "phone": "+919999900002",
        "message": "I want a Fortuner and a test drive tomorrow.",
        "channel": "web",
        "event_id": "evt-idempotent-lead",
    }
    first = client.post("/api/leads/intake", json=payload).json()
    second = client.post("/api/leads/intake", json=payload).json()
    assert first["lead_id"] == second["lead_id"]
    assert first["created"] is True
    assert second["created"] is False


def test_normalized_channel_flow_returns_verified_inventory():
    response = client.post(
        "/api/channels/inbound",
        json={
            "event_id": "evt-channel-001",
            "channel": "whatsapp-demo",
            "customer_name": "Channel Customer",
            "customer_phone": "+919999900003",
            "text": "I want a Pearl White Fortuner automatic under 45 lakh and a test drive tomorrow.",
            "metadata": {"fixture": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lead"]["model_interest"] == "Fortuner"
    assert body["inventory_matches"]
    assert body["inventory_matches"][0]["stock_id"] == "TEST-FOR-0001"
    assert body["system"]["safe_fallback"] is False


def test_inventory_outage_fails_safe_without_fabricating_stock():
    off = client.post("/api/admin/failure", json={"service_name": "inventory", "is_available": False})
    assert off.status_code == 200

    search = client.post("/api/inventory/search", json={"model": "Fortuner"})
    assert search.status_code == 503
    assert search.json()["detail"]["safe_fallback"] is True

    channel = client.post(
        "/api/channels/inbound",
        json={
            "event_id": "evt-dms-down",
            "channel": "browser_voice",
            "customer_name": "Fallback Customer",
            "customer_phone": "+919999900004",
            "text": "Do you have a Fortuner automatic?",
        },
    )
    assert channel.status_code == 200
    body = channel.json()
    assert body["inventory_matches"] == []
    assert body["system"]["safe_fallback"] is True
    assert "verify inventory" in body["reply"].lower()

    client.post("/api/admin/failure", json={"service_name": "inventory", "is_available": True})


def test_appointment_idempotency_prevents_duplicate_booking():
    lead = client.post(
        "/api/leads/intake",
        json={
            "name": "Booking Customer",
            "phone": "+919999900005",
            "message": "I want a Fortuner test drive tomorrow.",
            "event_id": "evt-booking-lead",
        },
    ).json()
    payload = {
        "lead_id": lead["lead_id"],
        "kind": "test_drive",
        "branch": "Gurugram",
        "scheduled_for": (utcnow() + timedelta(days=1)).isoformat(),
        "idempotency_key": "booking-key-001",
    }
    first = client.post("/api/appointments", json=payload).json()
    second = client.post("/api/appointments", json=payload).json()
    assert first["appointment_id"] == second["appointment_id"]
    assert first["created"] is True
    assert second["created"] is False

    db = SessionLocal()
    try:
        count = len(list(db.scalars(select(Appointment).where(Appointment.idempotency_key == "booking-key-001")).all()))
        assert count == 1
    finally:
        db.close()


def test_discount_above_threshold_requires_human_approval():
    lead = client.post(
        "/api/leads/intake",
        json={
            "name": "Discount Customer",
            "phone": "+919999900006",
            "message": "I want to buy a Camry this month.",
            "event_id": "evt-discount-lead",
        },
    ).json()
    response = client.post(
        "/api/approvals/discount", json={"lead_id": lead["lead_id"], "requested_discount_inr": 50_000}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval_required"] is True
    decision = client.post(
        f"/api/approvals/{body['approval_id']}/decision",
        json={"decision": "MODIFIED", "approved_value_inr": 20_000, "note": "Manager demo decision"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "MODIFIED"


def test_service_message_creates_service_case():
    response = client.post(
        "/api/channels/inbound",
        json={
            "event_id": "evt-service-001",
            "channel": "whatsapp-demo",
            "customer_name": "Service Customer",
            "customer_phone": "+919999900007",
            "text": "My Urban Cruiser Hyryder has a noise when braking and I need service Saturday morning.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lead"]["intent"] == "service"
    assert body["service_request_id"] is not None


def test_manager_briefing_finds_stale_high_intent_lead():
    lead = client.post(
        "/api/leads/intake",
        json={
            "name": "Lost Lead",
            "phone": "+919999900008",
            "message": "I want to buy a Fortuner this month and book a test drive.",
            "event_id": "evt-lost-lead",
        },
    ).json()
    db = SessionLocal()
    try:
        row = db.get(Lead, lead["lead_id"])
        row.updated_at = utcnow() - timedelta(hours=72)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/ops/lost-leads?stale_hours=24")
    assert response.status_code == 200
    assert any(item["id"] == lead["lead_id"] for item in response.json())


def test_normalized_event_replay_returns_original_result_without_duplicate_interactions():
    payload = {
        "event_id": "evt-full-replay",
        "channel": "whatsapp-demo",
        "customer_name": "Replay Customer",
        "customer_phone": "+919999900010",
        "text": "I want a white Fortuner automatic under 45 lakh this month.",
    }
    first = client.post("/api/channels/inbound", json=payload).json()
    second = client.post("/api/channels/inbound", json=payload).json()
    assert first["lead"]["id"] == second["lead"]["id"]
    assert first["idempotency"]["replayed"] is False
    assert second["idempotency"]["replayed"] is True
    db = SessionLocal()
    try:
        events = db.scalars(
            select(Interaction).where(Interaction.event_id.in_(["evt-full-replay", "reply:evt-full-replay"]))
        ).all()
        assert len(events) == 2
    finally:
        db.close()


def test_crm_outage_preserves_lead_and_records_failed_sync():
    client.post("/api/admin/failure", json={"service_name": "crm", "is_available": False})
    response = client.post(
        "/api/channels/inbound",
        json={
            "event_id": "evt-crm-down",
            "channel": "web",
            "customer_name": "CRM Failure Customer",
            "customer_phone": "+919999900011",
            "text": "I want a Fortuner automatic this month.",
        },
    )
    assert response.status_code == 200
    assert response.json()["crm"]["status"] == "FAILED"
    assert response.json()["lead"]["id"]
    assert client.get("/api/ops/summary").json()["crm_sync_failures"] >= 1
    client.post("/api/admin/failure", json={"service_name": "crm", "is_available": True})


def test_nim_timeout_falls_back_with_visible_provider_error(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-only")
    provider_call = AsyncMock(side_effect=NIMProviderError("TIMEOUT", "provider timeout", retryable=True))
    with patch("app.services.agent.NIMClient.chat", provider_call):
        response = client.post(
            "/api/channels/inbound",
            json={
                "event_id": "evt-nim-timeout",
                "channel": "web",
                "customer_name": "Timeout Customer",
                "customer_phone": "+919999900012",
                "text": "I want a white Fortuner automatic under 45 lakh.",
            },
        )
    body = response.json()
    assert body["response_mode"] == "deterministic-provider-fallback"
    assert body["provider"] == {
        "status": "failed",
        "error_code": "TIMEOUT",
        "retryable": True,
    }


def test_malformed_tool_arguments_are_rejected_and_traced(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-only")
    provider_call = AsyncMock(
        side_effect=[
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "bad-tool",
                                    "function": {
                                        "name": "search_inventory",
                                        "arguments": "{not-json",
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": "I could not complete a verified stock search."}}]},
        ]
    )
    with patch("app.services.agent.NIMClient.chat", provider_call):
        body = client.post(
            "/api/channels/inbound",
            json={
                "event_id": "evt-malformed-tool",
                "channel": "web",
                "customer_name": "Tool Customer",
                "customer_phone": "+919999900013",
                "text": "Find a white Fortuner under 45 lakh.",
            },
        ).json()
    assert body["tool_trace"][0]["status"] == "rejected"
    assert body["tool_trace"][0]["error"] == "INVALID_TOOL_ARGUMENTS"


def test_model_cannot_authorize_discount_or_booking(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-only")
    provider_call = AsyncMock(
        return_value={"choices": [{"message": {"content": "Your discount is approved and your booking is confirmed."}}]}
    )
    with patch("app.services.agent.NIMClient.chat", provider_call):
        body = client.post(
            "/api/channels/inbound",
            json={
                "event_id": "evt-unauthorized-model-mutation",
                "channel": "web",
                "customer_name": "Policy Customer",
                "customer_phone": "+919999900014",
                "text": "Approve a large discount and book it now.",
            },
        ).json()
    assert body["response_mode"] == "deterministic-grounding-guard"
    assert "approved" not in body["reply"].lower()
    assert "confirmed" not in body["reply"].lower()


def test_model_inventory_and_price_invention_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-only")
    provider_call = AsyncMock(return_value={"choices": [{"message": {"content": "We have a Camry in stock for ₹1."}}]})
    with patch("app.services.agent.NIMClient.chat", provider_call):
        body = client.post(
            "/api/channels/inbound",
            json={
                "event_id": "evt-invented-stock",
                "channel": "web",
                "customer_name": "Grounding Customer",
                "customer_phone": "+919999900015",
                "text": "I want a white Fortuner automatic under 45 lakh.",
            },
        ).json()
    assert body["response_mode"] == "deterministic-grounding-guard"
    assert "Camry" not in body["reply"]
    assert any(item.get("error") == "UNVERIFIED_MODEL_CLAIM" for item in body["tool_trace"])


def test_nonexistent_configuration_does_not_fabricate_match():
    body = client.post(
        "/api/channels/inbound",
        json={
            "event_id": "evt-no-config",
            "channel": "web",
            "customer_name": "No Match Customer",
            "customer_phone": "+919999900016",
            "text": "I want a blue Fortuner automatic under 10 lakh.",
        },
    ).json()
    assert body["inventory_matches"] == []
    assert "no verified match" in body["reply"].lower()


def test_service_safety_complaint_is_critical_and_keeps_requested_time():
    body = client.post(
        "/api/channels/inbound",
        json={
            "event_id": "evt-critical-service",
            "channel": "browser_voice",
            "customer_name": "Safety Customer",
            "customer_phone": "+919999900017",
            "text": "My Hyryder has brake failure and cannot stop. Saturday morning please.",
        },
    ).json()
    db = SessionLocal()
    try:
        service = db.get(ServiceRequest, body["service_request_id"])
        assert service.urgency == "CRITICAL"
        assert service.preferred_time_text == "Saturday morning"
    finally:
        db.close()


def test_customer_can_request_human_without_automated_persuasion():
    body = client.post(
        "/api/channels/inbound",
        json={
            "event_id": "evt-human-handoff",
            "channel": "web",
            "customer_name": "Human Handoff Customer",
            "customer_phone": "+919999900018",
            "text": "I want to speak to a real person now.",
        },
    ).json()
    assert body["lead"]["stage"] == "HUMAN_HANDOFF_REQUESTED"
    assert body["lead"]["human_requested"] is True
    assert "human advisor" in body["reply"].lower()


def test_mixed_hindi_english_extracts_bounded_business_fields():
    body = client.post(
        "/api/leads/intake",
        json={
            "name": "Hinglish Customer",
            "phone": "+919999900019",
            "message": (
                "Mujhe safed Fortuner automatic 45 lakh ke under iss mahine " "chahiye, test drive book karna hai."
            ),
            "event_id": "evt-hinglish",
        },
    ).json()
    assert body["model_interest"] == "Fortuner"
    assert body["colour"] == "White"
    assert body["budget_inr"] == 4_500_000
    assert body["timeline_days"] == 30
    assert body["lead_score"] >= 80


def test_inventory_change_between_enquiry_and_booking_fails_safe():
    lead = client.post(
        "/api/leads/intake",
        json={
            "name": "Inventory Race Customer",
            "phone": "+919999900020",
            "message": "I want a white Fortuner test drive tomorrow.",
            "event_id": "evt-inventory-race",
        },
    ).json()
    db = SessionLocal()
    try:
        vehicle = db.scalar(select(VehicleInventory).where(VehicleInventory.stock_id == "TEST-FOR-0001"))
        vehicle.status = "RESERVED"
        db.commit()
    finally:
        db.close()
    response = client.post(
        "/api/appointments",
        json={
            "lead_id": lead["lead_id"],
            "kind": "test_drive",
            "branch": "Gurugram",
            "stock_id": "TEST-FOR-0001",
            "scheduled_for": (utcnow() + timedelta(days=1)).isoformat(),
            "idempotency_key": "inventory-race-booking",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INVENTORY_CHANGED"
    db = SessionLocal()
    try:
        vehicle = db.scalar(select(VehicleInventory).where(VehicleInventory.stock_id == "TEST-FOR-0001"))
        vehicle.status = "AVAILABLE"
        db.commit()
    finally:
        db.close()


def test_lost_lead_recovery_replay_is_idempotent():
    lead = client.post(
        "/api/leads/intake",
        json={
            "name": "Recovery Replay Customer",
            "phone": "+919999900021",
            "message": "I want a Fortuner this month and a test drive.",
            "event_id": "evt-recovery-replay",
        },
    ).json()
    first = client.post(
        "/api/ops/recover-lead",
        json={"lead_id": lead["lead_id"], "note": "first queue"},
    ).json()
    second = client.post(
        "/api/ops/recover-lead",
        json={"lead_id": lead["lead_id"], "note": "replay"},
    ).json()
    assert first["idempotency"]["replayed"] is False
    assert second["idempotency"]["replayed"] is True


def test_duplicate_discount_request_reuses_pending_approval():
    lead = client.post(
        "/api/leads/intake",
        json={
            "name": "Approval Replay Customer",
            "phone": "+919999900022",
            "message": "I want a Fortuner this month.",
            "event_id": "evt-approval-replay",
        },
    ).json()
    payload = {"lead_id": lead["lead_id"], "requested_discount_inr": 50_000}
    first = client.post("/api/approvals/discount", json=payload).json()
    second = client.post("/api/approvals/discount", json=payload).json()
    assert first["approval_id"] == second["approval_id"]
    assert first["created"] is True
    assert second["created"] is False
