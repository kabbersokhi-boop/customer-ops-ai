from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./customer_ops.db"
    nvidia_nim_api_key: str = ""
    nvidia_nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_nim_model: str = "z-ai/glm-5.3-flash"
    nvidia_nim_timeout_seconds: float = Field(default=25.0, ge=1, le=120)
    nvidia_nim_max_retries: int = Field(default=2, ge=0, le=5)
    airtable_api_key: str = ""
    airtable_base_id: str = ""
    airtable_base_web_url: str = ""
    airtable_enabled: bool = False
    airtable_timeout_seconds: float = Field(default=10.0, ge=1, le=60)
    airtable_max_retries: int = Field(default=2, ge=0, le=5)
    airtable_base_url: str = "https://api.airtable.com/v0"
    airtable_customers_table: str = "Customers"
    airtable_leads_table: str = "Leads"
    airtable_activities_table: str = "Activities"
    airtable_appointments_table: str = "Appointments"
    airtable_approvals_table: str = "Approval Requests"
    orchestration_mode: Literal["direct", "n8n"] = "direct"
    n8n_inbound_webhook_url: str = ""
    n8n_appointment_webhook_url: str = ""
    n8n_ui_base_url: str = ""
    admin_api_key: str = ""
    app_env: str = "development"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
