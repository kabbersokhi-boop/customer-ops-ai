from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class VehicleInventory(Base):
    __tablename__ = "vehicle_inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    model: Mapped[str] = mapped_column(String(80), index=True)
    variant: Mapped[str] = mapped_column(String(120))
    fuel_type: Mapped[str] = mapped_column(String(40))
    transmission: Mapped[str] = mapped_column(String(40))
    colour: Mapped[str] = mapped_column(String(60), index=True)
    branch: Mapped[str] = mapped_column(String(80), index=True)
    demo_price_inr: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="AVAILABLE", index=True)
    test_drive_vehicle: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_delivery_days: Mapped[int] = mapped_column(Integer, default=7)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(120), unique=True, index=True, nullable=True)
    source_channel: Mapped[str] = mapped_column(String(40), default="web")
    intent: Mapped[str] = mapped_column(String(40), default="sales")
    model_interest: Mapped[str | None] = mapped_column(String(80), nullable=True)
    budget_inr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    colour_preference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    transmission_preference: Mapped[str | None] = mapped_column(String(40), nullable=True)
    timeline_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trade_in_vehicle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lead_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    stage: Mapped[str] = mapped_column(String(50), default="NEW", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    crm_record_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    crm_sync_status: Mapped[str] = mapped_column(String(30), default="NOT_SYNCED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    branch: Mapped[str] = mapped_column(String(80))
    stock_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(40), default="BOOKED")
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(120), unique=True, index=True, nullable=True)
    vehicle_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registration: Mapped[str | None] = mapped_column(String(30), nullable=True)
    issue_summary: Mapped[str] = mapped_column(Text)
    urgency: Mapped[str] = mapped_column(String(30), default="NORMAL")
    stage: Mapped[str] = mapped_column(String(40), default="OPEN", index=True)
    preferred_time_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(40), index=True)
    direction: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    action: Mapped[str] = mapped_column(String(60))
    requested_value: Mapped[str] = mapped_column(String(120))
    recommendation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    decision_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SystemState(Base):
    __tablename__ = "system_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(80), unique=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    failure_rate: Mapped[float] = mapped_column(Float, default=0.0)


class ChannelEventReceipt(Base):
    __tablename__ = "channel_event_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    response_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CrmSync(Base):
    __tablename__ = "crm_syncs"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="airtable")
    status: Mapped[str] = mapped_column(String(30), index=True)
    record_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    record_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    operation: Mapped[str | None] = mapped_column(String(30), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
