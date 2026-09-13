from app.core.config import settings
from app.services.orchestration import demo_orchestration_config


def test_manager_workspace_keeps_orchestration_proof_behind_technical_details():
    markup = open("app/static/index.html", encoding="utf-8").read()
    assert "/api/demo/config" in markup
    assert "Technical details" in markup
    assert "openTechnicalDetails" in markup
    assert 'id="technicalDrawer"' in markup
    assert 'id="pipeline"' in markup
    assert 'id="crmTrace"' in markup
    assert 'id="auditTrace"' in markup
    assert 'id="n8nLink"' in markup
    assert "Open n8n executions" in markup
    assert "/api/ops/crm-sync" in markup
    assert "/api/ops/audit" in markup


def test_manager_workspace_prioritizes_exceptions_over_customer_context():
    markup = open("app/static/index.html", encoding="utf-8").read()
    assert "Booking completion rate" in markup
    assert "Recent service appointments" in markup
    assert markup.index('id="attentionTitle"') < markup.index('id="appointmentsTitle"')
    assert markup.index('id="appointmentsTitle"') < markup.index('id="contextTitle"')
    assert "lead score" not in markup.lower()


def test_appointment_workflow_forwards_confirmed_contact_fields():
    workflow = open("n8n/appointment-confirmation.json", encoding="utf-8").read()
    assert '"name":"contact_name"' in workflow
    assert '"name":"contact_phone"' in workflow
    assert '"name":"contact_email"' in workflow
    assert '"name":"service_request_id"' in workflow
    assert '"name":"slot_id"' in workflow
    assert "$json.confirmed" in workflow
    assert "Booking is not confirmed" in workflow
    assert "Create Idempotent Appointment" in workflow


def test_booking_crm_sync_refreshes_customer_projection_before_appointment():
    source = open("app/services/crm.py", encoding="utf-8").read()
    assert "customer = db.get(Customer, lead.customer_id)" in source
    assert "await sync_customer(db, customer)" in source
    assert source.index("await sync_customer(db, customer)") < source.index('"Appointment ID": str(appointment.id)')


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
