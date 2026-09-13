#!/usr/bin/env python3
import argparse
import asyncio
import json
import sys
from collections.abc import Iterable

import httpx

from app.core.config import settings
from app.providers.nim import NIMClient, NIMProviderError

EXPECTED_AIRTABLE_FIELDS = {
    "Customers": {"Customer ID", "Name", "Phone", "Email", "Created At"},
    "Leads": {
        "Lead ID",
        "Customer ID",
        "Channel",
        "Intent",
        "Model Interest",
        "Budget INR",
        "Colour",
        "Transmission",
        "Timeline Days",
        "Trade In",
        "Lead Score",
        "Stage",
        "Summary",
    },
    "Activities": {"Activity ID", "Lead ID", "Direction", "Channel", "Intent", "Content", "Created At"},
    "Appointments": {
        "Appointment ID",
        "Lead ID",
        "Kind",
        "Branch",
        "Stock ID",
        "Scheduled For",
        "Status",
        "Idempotency Key",
    },
    "Approval Requests": {
        "Approval ID",
        "Lead ID",
        "Action",
        "Requested Value",
        "Recommendation",
        "Status",
        "Decision Value",
        "Created At",
    },
}


def _configured_airtable_tables() -> dict[str, set[str]]:
    return {
        settings.airtable_customers_table: EXPECTED_AIRTABLE_FIELDS["Customers"],
        settings.airtable_leads_table: EXPECTED_AIRTABLE_FIELDS["Leads"],
        settings.airtable_activities_table: EXPECTED_AIRTABLE_FIELDS["Activities"],
        settings.airtable_appointments_table: EXPECTED_AIRTABLE_FIELDS["Appointments"],
        settings.airtable_approvals_table: EXPECTED_AIRTABLE_FIELDS["Approval Requests"],
    }


async def verify_nim() -> bool:
    if not settings.nvidia_nim_api_key:
        print("NIM: not configured", file=sys.stderr)
        return False
    tool = {
        "type": "function",
        "function": {
            "name": "search_inventory",
            "description": "Search verified synthetic dealership inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "colour": {"type": "string"},
                    "transmission": {"type": "string"},
                    "max_budget_inr": {"type": "integer", "minimum": 0},
                },
                "required": ["model"],
                "additionalProperties": False,
            },
        },
    }
    try:
        response = await NIMClient().chat(
            [
                {"role": "system", "content": "Call search_inventory before answering inventory questions."},
                {"role": "user", "content": "Find a white Fortuner automatic under 45 lakh."},
            ],
            [tool],
        )
    except NIMProviderError as exc:
        print(f"NIM: failed ({exc.code}, retryable={exc.retryable})", file=sys.stderr)
        return False
    message = response["choices"][0].get("message") or {}
    calls = message.get("tool_calls") or []
    if not calls:
        print("NIM: failed (model did not call the inventory tool)", file=sys.stderr)
        return False
    function = calls[0].get("function") or {}
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError:
        print("NIM: failed (tool arguments were malformed JSON)", file=sys.stderr)
        return False
    valid = function.get("name") == "search_inventory" and str(arguments.get("model", "")).lower() == "fortuner"
    if not valid:
        print("NIM: failed (tool name or required model argument was invalid)", file=sys.stderr)
        return False
    print(
        f"NIM: ok model={settings.nvidia_nim_model} tool=search_inventory "
        f"argument_keys={','.join(sorted(arguments))}"
    )
    return True


async def verify_airtable() -> bool:
    if not settings.airtable_api_key or not settings.airtable_base_id:
        print("Airtable: not configured", file=sys.stderr)
        return False
    if not settings.airtable_base_id.startswith("app"):
        print("Airtable: failed (AIRTABLE_BASE_ID must start with 'app')", file=sys.stderr)
        return False
    url = f"https://api.airtable.com/v0/meta/bases/{settings.airtable_base_id}/tables"
    headers = {"Authorization": f"Bearer {settings.airtable_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=settings.airtable_timeout_seconds) as client:
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        print("Airtable: failed (metadata request timed out)", file=sys.stderr)
        return False
    except httpx.RequestError:
        print("Airtable: failed (metadata network error)", file=sys.stderr)
        return False
    if response.status_code >= 400:
        print(f"Airtable: failed (metadata HTTP {response.status_code})", file=sys.stderr)
        return False
    body = response.json()
    actual = {
        table.get("name", ""): {field.get("name", "") for field in table.get("fields", [])}
        for table in body.get("tables", [])
    }
    expected = _configured_airtable_tables()
    failures: list[str] = []
    for table_name, expected_fields in expected.items():
        if table_name not in actual:
            failures.append(f"missing table {table_name}")
            continue
        missing_fields = sorted(expected_fields - actual[table_name])
        if missing_fields:
            failures.append(f"{table_name} missing fields: {', '.join(missing_fields)}")
    if failures:
        for failure in failures:
            print(f"Airtable: failed ({failure})", file=sys.stderr)
        return False
    print(f"Airtable: ok base_access=true tables={len(expected)} schema=compatible")
    return True


async def run(selected: Iterable[str]) -> int:
    checks = []
    if "nim" in selected:
        checks.append(await verify_nim())
    if "airtable" in selected:
        checks.append(await verify_airtable())
    return 0 if checks and all(checks) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify live provider access without printing credentials or records.")
    parser.add_argument("providers", nargs="*", choices=["nim", "airtable"])
    args = parser.parse_args()
    return asyncio.run(run(args.providers or ["nim", "airtable"]))


if __name__ == "__main__":
    raise SystemExit(main())
