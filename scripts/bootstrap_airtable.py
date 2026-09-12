#!/usr/bin/env python3
import argparse
import sys
from dataclasses import dataclass

import httpx

from app.core.config import settings


def _text(name: str) -> dict:
    return {"name": name, "type": "singleLineText"}


def _long_text(name: str) -> dict:
    return {"name": name, "type": "multilineText"}


def _number(name: str) -> dict:
    return {"name": name, "type": "number", "options": {"precision": 0}}


TABLE_SCHEMAS = {
    "Customers": [
        _text("Customer ID"),
        _text("Name"),
        _text("Phone"),
        _text("Email"),
        _text("Created At"),
    ],
    "Leads": [
        _text("Lead ID"),
        _text("Customer ID"),
        _text("Channel"),
        _text("Intent"),
        _text("Model Interest"),
        _number("Budget INR"),
        _text("Colour"),
        _text("Transmission"),
        _number("Timeline Days"),
        _text("Trade In"),
        _number("Lead Score"),
        _text("Stage"),
        _long_text("Summary"),
    ],
    "Activities": [
        _text("Activity ID"),
        _text("Lead ID"),
        _text("Direction"),
        _text("Channel"),
        _text("Intent"),
        _long_text("Content"),
        _text("Created At"),
    ],
    "Appointments": [
        _text("Appointment ID"),
        _text("Lead ID"),
        _text("Kind"),
        _text("Branch"),
        _text("Stock ID"),
        _text("Scheduled For"),
        _text("Status"),
        _text("Idempotency Key"),
    ],
    "Approval Requests": [
        _text("Approval ID"),
        _text("Lead ID"),
        _text("Action"),
        _text("Requested Value"),
        _long_text("Recommendation"),
        _text("Status"),
        _text("Decision Value"),
        _text("Created At"),
    ],
}


@dataclass(frozen=True)
class SchemaOperation:
    action: str
    table_name: str
    table_id: str | None = None
    field: dict | None = None


def configured_table_schemas() -> dict[str, list[dict]]:
    return {
        settings.airtable_customers_table: TABLE_SCHEMAS["Customers"],
        settings.airtable_leads_table: TABLE_SCHEMAS["Leads"],
        settings.airtable_activities_table: TABLE_SCHEMAS["Activities"],
        settings.airtable_appointments_table: TABLE_SCHEMAS["Appointments"],
        settings.airtable_approvals_table: TABLE_SCHEMAS["Approval Requests"],
    }


def build_plan(existing_tables: list[dict], expected: dict[str, list[dict]]) -> list[SchemaOperation]:
    actual = {table.get("name", ""): table for table in existing_tables}
    operations: list[SchemaOperation] = []
    for table_name, expected_fields in expected.items():
        table = actual.get(table_name)
        if not table:
            operations.append(SchemaOperation(action="create_table", table_name=table_name))
            continue
        actual_fields = {field.get("name", "") for field in table.get("fields", [])}
        for field in expected_fields:
            if field["name"] not in actual_fields:
                operations.append(
                    SchemaOperation(
                        action="create_field",
                        table_name=table_name,
                        table_id=table.get("id"),
                        field=field,
                    )
                )
    return operations


def _error_type(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return "UNKNOWN"
    if isinstance(error, dict):
        return str(error.get("type") or "UNKNOWN")[:80]
    return str(error)[:80]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create only missing Airtable CRM tables and fields. Dry-run unless --apply is supplied."
    )
    parser.add_argument("--apply", action="store_true", help="Apply the displayed additive schema operations.")
    args = parser.parse_args()
    if not settings.airtable_api_key or not settings.airtable_base_id:
        print("Airtable schema: not configured", file=sys.stderr)
        return 1
    if not settings.airtable_base_id.startswith("app"):
        print("Airtable schema: AIRTABLE_BASE_ID must start with 'app'", file=sys.stderr)
        return 1

    headers = {
        "Authorization": f"Bearer {settings.airtable_api_key}",
        "Content-Type": "application/json",
    }
    root = f"https://api.airtable.com/v0/meta/bases/{settings.airtable_base_id}"
    with httpx.Client(timeout=settings.airtable_timeout_seconds, headers=headers) as client:
        response = client.get(f"{root}/tables")
        if response.status_code >= 400:
            print(
                f"Airtable schema: metadata HTTP {response.status_code} ({_error_type(response)})",
                file=sys.stderr,
            )
            return 1
        plan = build_plan(response.json().get("tables", []), configured_table_schemas())
        if not plan:
            print("Airtable schema: compatible; no changes required")
            return 0
        for operation in plan:
            suffix = f".{operation.field['name']}" if operation.field else ""
            print(f"plan={operation.action} target={operation.table_name}{suffix}")
        if not args.apply:
            print("Airtable schema: dry run only; rerun with --apply after reviewing the additive plan")
            return 2

        expected = configured_table_schemas()
        for operation in plan:
            if operation.action == "create_table":
                response = client.post(
                    f"{root}/tables",
                    json={"name": operation.table_name, "fields": expected[operation.table_name]},
                )
            else:
                response = client.post(
                    f"{root}/tables/{operation.table_id}/fields",
                    json=operation.field,
                )
            if response.status_code >= 400:
                print(
                    f"Airtable schema: {operation.action} failed with HTTP {response.status_code} "
                    f"({_error_type(response)})",
                    file=sys.stderr,
                )
                return 1
        print(f"Airtable schema: applied {len(plan)} additive operations")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
