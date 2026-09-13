from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InventorySearch(BaseModel):
    model: str | None = None
    max_budget_inr: int | None = Field(default=None, ge=0)
    transmission: str | None = None
    colour: str | None = None
    branch: str | None = None


class LeadIntake(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=6, max_length=30)
    message: str = Field(min_length=2, max_length=4000)
    channel: str = "web"
    event_id: str | None = None


class ChannelEvent(BaseModel):
    event_id: str = Field(min_length=3, max_length=120)
    channel: str = Field(default="whatsapp-demo", max_length=40)
    customer_name: str = Field(min_length=2, max_length=120)
    customer_phone: str = Field(min_length=6, max_length=30)
    text: str = Field(min_length=1, max_length=4000)
    conversation_lead_id: int | None = Field(default=None, ge=1)
    occurred_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AppointmentCreate(BaseModel):
    lead_id: int
    kind: str = "test_drive"
    branch: str
    stock_id: str | None = Field(default=None, max_length=64)
    scheduled_for: datetime
    idempotency_key: str = Field(min_length=4, max_length=120)
    contact_name: str | None = Field(default=None, min_length=2, max_length=120)
    contact_phone: str | None = Field(default=None, min_length=6, max_length=30)
    contact_email: str | None = Field(
        default=None,
        max_length=180,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    )


class DiscountRequest(BaseModel):
    lead_id: int
    requested_discount_inr: int = Field(gt=0)


class ApprovalDecision(BaseModel):
    decision: str
    approved_value_inr: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=1000)


class ServiceIntake(BaseModel):
    name: str
    phone: str
    message: str
    vehicle_model: str | None = None
    registration: str | None = None
    preferred_time_text: str | None = None
    channel: str = "web"
    event_id: str | None = None


class FailureToggle(BaseModel):
    service_name: str = Field(pattern="^(inventory|crm|messaging)$")
    is_available: bool


class LostLeadRecovery(BaseModel):
    lead_id: int
    note: str | None = None
