from app.core.config import settings
from app.services.orchestration import demo_orchestration_config


def test_demo_console_keeps_orchestration_proof_behind_technical_details():
    markup = open("app/static/index.html", encoding="utf-8").read()
    assert "/api/demo/config" in markup
    assert "Technical details" in markup
    assert "openTrace" in markup
    assert "orchestrationTrace" in markup
    assert "/api/ops/crm-sync" in markup
    assert "/api/ops/audit" in markup


def test_direct_mode_uses_fastapi_routes(monkeypatch):
    monkeypatch.setattr(settings, "orchestration_mode", "direct")
    config = demo_orchestration_config()
    assert config["status"] == "ready"
    assert config["routes"]["inbound"] == {
        "transport": "direct",
        "url": "/api/channels/inbound",
        "workflow_id": None,
    }
    assert config["routes"]["appointment"]["transport"] == "direct"


def test_n8n_mode_exposes_safe_webhook_routes(monkeypatch):
    monkeypatch.setattr(settings, "orchestration_mode", "n8n")
    monkeypatch.setattr(settings, "n8n_inbound_webhook_url", "http://localhost:5678/webhook/customer-ops/inbound")
    monkeypatch.setattr(
        settings,
        "n8n_appointment_webhook_url",
        "http://localhost:5678/webhook/customer-ops/appointments",
    )
    monkeypatch.setattr(settings, "n8n_ui_base_url", "")
    config = demo_orchestration_config()
    assert config["status"] == "ready"
    assert config["routes"]["inbound"]["transport"] == "n8n"
    assert config["routes"]["appointment"]["workflow_id"] == "coa-appointment-confirm"
    assert config["n8n_ui_base_url"] == "http://localhost:5678"


def test_n8n_mode_degrades_unsafe_or_missing_routes(monkeypatch):
    monkeypatch.setattr(settings, "orchestration_mode", "n8n")
    monkeypatch.setattr(settings, "n8n_inbound_webhook_url", "https://user:secret@example.com/webhook")
    monkeypatch.setattr(settings, "n8n_appointment_webhook_url", "")
    monkeypatch.setattr(settings, "n8n_ui_base_url", "javascript:alert(1)")
    config = demo_orchestration_config()
    assert config["status"] == "degraded"
    assert config["fallback_routes"] == ["inbound", "appointment"]
    assert all(route["transport"] == "direct" for route in config["routes"].values())
    assert config["n8n_ui_base_url"] is None
