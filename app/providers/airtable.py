import asyncio
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.core.config import settings


class AirtableProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class AirtableRecord:
    mode: str
    record_id: str
    record_url: str | None
    operation: str


class AirtableCRM:
    """Provider adapter; domain services never depend on Airtable schema details."""

    TABLES = {
        "customer": lambda: settings.airtable_customers_table,
        "lead": lambda: settings.airtable_leads_table,
        "activity": lambda: settings.airtable_activities_table,
        "appointment": lambda: settings.airtable_appointments_table,
        "approval": lambda: settings.airtable_approvals_table,
    }

    def __init__(self) -> None:
        self.enabled = bool(
            settings.airtable_enabled
            and settings.airtable_api_key
            and settings.airtable_api_key != "replace_me"
            and settings.airtable_base_id
            and settings.airtable_base_id != "replace_me"
        )

    def _table(self, entity_type: str) -> str:
        try:
            return self.TABLES[entity_type]()
        except KeyError as exc:
            raise ValueError(f"Unsupported CRM entity type: {entity_type}") from exc

    def _table_url(self, table: str) -> str:
        return f"{settings.airtable_base_url.rstrip('/')}/{settings.airtable_base_id}/{quote(table, safe='')}"

    @staticmethod
    def _formula(field: str, value: str) -> str:
        escaped_field = field.replace("}", "")
        escaped_value = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"{{{escaped_field}}}='{escaped_value}'"

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = {"Authorization": f"Bearer {settings.airtable_api_key}", "Content-Type": "application/json"}
        attempts = settings.airtable_max_retries + 1
        async with httpx.AsyncClient(timeout=settings.airtable_timeout_seconds) as client:
            for attempt in range(attempts):
                try:
                    response = await client.request(method, url, headers=headers, **kwargs)
                except httpx.TimeoutException as exc:
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0.25 * (2**attempt))
                        continue
                    raise AirtableProviderError("TIMEOUT", "Airtable timed out", retryable=True) from exc
                except httpx.RequestError as exc:
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0.25 * (2**attempt))
                        continue
                    raise AirtableProviderError("NETWORK_ERROR", "Airtable request failed", retryable=True) from exc
                if response.status_code in {408, 429, 500, 502, 503, 504} and attempt + 1 < attempts:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                if response.status_code >= 400:
                    raise AirtableProviderError(
                        f"HTTP_{response.status_code}",
                        "Airtable rejected the record sync",
                        retryable=response.status_code in {408, 429, 500, 502, 503, 504},
                    )
                return response
        raise AirtableProviderError("UNKNOWN", "Airtable request failed")

    async def upsert(self, entity_type: str, external_field: str, external_id: str, fields: dict) -> AirtableRecord:
        table = self._table(entity_type)
        if not self.enabled:
            return AirtableRecord(
                mode="mock",
                record_id=f"mock_{entity_type}_{external_id}",
                record_url=None,
                operation="upsert",
            )

        table_url = self._table_url(table)
        lookup = await self._request(
            "GET",
            table_url,
            params={"filterByFormula": self._formula(external_field, external_id), "maxRecords": 1},
        )
        records = lookup.json().get("records", [])
        if records:
            record_id = records[0]["id"]
            await self._request("PATCH", f"{table_url}/{record_id}", json={"fields": fields, "typecast": True})
            operation = "updated"
        else:
            created = await self._request("POST", table_url, json={"fields": fields, "typecast": True})
            record_id = created.json()["id"]
            operation = "created"
        record_url = settings.airtable_base_web_url or f"https://airtable.com/{settings.airtable_base_id}"
        return AirtableRecord(mode="live", record_id=record_id, record_url=record_url, operation=operation)

    async def sync_customer(self, fields: dict) -> AirtableRecord:
        return await self.upsert("customer", "Customer ID", str(fields["Customer ID"]), fields)

    async def sync_lead(self, fields: dict) -> AirtableRecord:
        return await self.upsert("lead", "Lead ID", str(fields["Lead ID"]), fields)

    async def sync_activity(self, fields: dict) -> AirtableRecord:
        return await self.upsert("activity", "Activity ID", str(fields["Activity ID"]), fields)

    async def sync_appointment(self, fields: dict) -> AirtableRecord:
        return await self.upsert("appointment", "Appointment ID", str(fields["Appointment ID"]), fields)

    async def sync_approval(self, fields: dict) -> AirtableRecord:
        return await self.upsert("approval", "Approval ID", str(fields["Approval ID"]), fields)
