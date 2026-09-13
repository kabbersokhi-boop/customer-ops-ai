from datetime import datetime
from unittest.mock import AsyncMock, patch

import uvloop
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import Appointment, Customer, CustomerProfile, Interaction, Lead, ServiceBookingContext, ServiceRequest
from app.providers.airtable import AirtableRecord
from app.services.crm import sync_appointment, sync_customer


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_customer_projection_contains_business_facing_vehicle_and_interaction_fields():
    db = _session()
    customer = Customer(name="Kabir Mehta", phone="+919900001111", email="kabir@example.com")
    db.add(customer)
    db.flush()
    db.add(
        CustomerProfile(
            customer_id=customer.id,
            vehicle_model="Fortuner",
            registration="HR26KM4000",
            preferred_branch="Gurugram",
        )
    )
    db.add(Interaction(customer_id=customer.id, channel="demo", direction="INBOUND", content="Book service"))
    db.commit()
    provider = AsyncMock(return_value=AirtableRecord("live", "rec-customer", None, "updated"))
    with patch("app.services.crm.AirtableCRM.sync_customer", provider):
        uvloop.run(sync_customer(db, customer))
    fields = provider.await_args.args[0]
    assert fields["Vehicle"] == "Fortuner"
    assert fields["Registration"] == "HR26KM4000"
    assert fields["Preferred Branch"] == "Gurugram"
    assert fields["Last Interaction"]


def test_service_appointment_projection_is_readable_and_keeps_technical_key():
    db = _session()
    customer = Customer(name="Kabir Mehta", phone="+919900001112", email="kabir@example.com")
    db.add(customer)
    db.flush()
    db.add(CustomerProfile(customer_id=customer.id, vehicle_model="Fortuner", registration="HR26KM4000"))
    lead = Lead(customer_id=customer.id, source_channel="demo", intent="service", stage="SERVICE_BOOKED")
    db.add(lead)
    db.flush()
    request = ServiceRequest(customer_id=customer.id, issue_summary="40,000 km scheduled service")
    db.add(request)
    db.flush()
    db.add(ServiceBookingContext(lead_id=lead.id, service_request_id=request.id, status="BOOKED"))
    appointment = Appointment(
        lead_id=lead.id,
        kind="service",
        branch="Gurugram",
        scheduled_for=datetime(2026, 9, 14, 10, 0),
        idempotency_key="service-projection-test",
    )
    db.add(appointment)
    db.commit()
    customer_provider = AsyncMock(return_value=AirtableRecord("live", "rec-customer", None, "updated"))
    appointment_provider = AsyncMock(return_value=AirtableRecord("live", "rec-appointment", None, "created"))
    with (
        patch("app.services.crm.AirtableCRM.sync_customer", customer_provider),
        patch("app.services.crm.AirtableCRM.sync_appointment", appointment_provider),
    ):
        uvloop.run(sync_appointment(db, appointment))
    fields = appointment_provider.await_args.args[0]
    assert fields["Customer"] == "Kabir Mehta"
    assert fields["Vehicle"] == "Fortuner"
    assert fields["Service Request"] == "40,000 km scheduled service"
    assert fields["Next Action"] == "Prepare service reception"
    assert fields["Idempotency Key"] == "service-projection-test"
