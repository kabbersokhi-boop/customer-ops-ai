#!/usr/bin/env python3
import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Appointment, ApprovalRequest, Customer, Interaction, Lead
from app.services.crm import sync_activity, sync_appointment, sync_approval, sync_customer, sync_lead
from scripts.seed_demo import main as seed_database

CONFIRMATION = "RESET_DEMO"


def _assert_demo_scope() -> None:
    database = make_url(settings.database_url)
    if database.host not in {None, "", "localhost", "127.0.0.1", "postgres"}:
        raise SystemExit(f"Refusing to reset non-local database host: {database.host}")
    if settings.app_env.lower() not in {"development", "demo", "test"}:
        raise SystemExit("Refusing to reset outside development/demo/test")
    if not settings.demo_controls_enabled:
        raise SystemExit("Refusing to reset while DEMO_CONTROLS_ENABLED is false")


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_database()


async def _airtable_records(client: httpx.AsyncClient, table: str) -> list[dict]:
    url = f"{settings.airtable_base_url.rstrip('/')}/{settings.airtable_base_id}/{quote(table, safe='')}"
    records: list[dict] = []
    offset = None
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        response = await client.get(url, params=params)
        response.raise_for_status()
        body = response.json()
        records.extend(body.get("records", []))
        offset = body.get("offset")
        if not offset:
            return records


async def reset_airtable(backup_dir: Path) -> Path:
    if not settings.airtable_enabled or not settings.airtable_api_key or not settings.airtable_base_id:
        raise SystemExit("Airtable is not configured")
    headers = {"Authorization": f"Bearer {settings.airtable_api_key}", "Content-Type": "application/json"}
    tables = [
        settings.airtable_customers_table,
        settings.airtable_leads_table,
        settings.airtable_activities_table,
        settings.airtable_appointments_table,
        settings.airtable_approvals_table,
    ]
    snapshot = {"created_at": datetime.now().isoformat(), "base_id": settings.airtable_base_id, "tables": {}}
    async with httpx.AsyncClient(timeout=settings.airtable_timeout_seconds, headers=headers) as client:
        for table in tables:
            records = await _airtable_records(client, table)
            snapshot["tables"][table] = records
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"airtable-before-reset-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        backup.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        for table, records in snapshot["tables"].items():
            url = f"{settings.airtable_base_url.rstrip('/')}/{settings.airtable_base_id}/{quote(table, safe='')}"
            ids = [record["id"] for record in records]
            for start in range(0, len(ids), 10):
                response = await client.delete(url, params=[("records[]", value) for value in ids[start : start + 10]])
                response.raise_for_status()
    return backup


async def project_baseline() -> None:
    db = SessionLocal()
    try:
        for customer in db.query(Customer).order_by(Customer.id):
            await sync_customer(db, customer)
        for lead in db.query(Lead).order_by(Lead.id):
            await sync_lead(db, lead)
        for activity in db.query(Interaction).order_by(Interaction.id):
            await sync_activity(db, activity)
        for appointment in db.query(Appointment).order_by(Appointment.id):
            await sync_appointment(db, appointment)
        for approval in db.query(ApprovalRequest).order_by(ApprovalRequest.id):
            await sync_approval(db, approval)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset only the explicitly configured local synthetic demo environment.")
    parser.add_argument("--confirm", required=True, help=f"Must be exactly {CONFIRMATION}")
    parser.add_argument("--database", action="store_true", help="Rebuild the local application schema and seed baseline.")
    parser.add_argument("--airtable", action="store_true", help="Snapshot and reset application-owned Airtable tables.")
    parser.add_argument("--backup-dir", default=".demo-backups", help="Ignored local directory for Airtable snapshots.")
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit("Confirmation phrase did not match")
    if not args.database and not args.airtable:
        raise SystemExit("Choose --database, --airtable, or both")
    _assert_demo_scope()
    if args.database:
        reset_database()
        print("Database reset to deterministic service-operations baseline.")
    if args.airtable:
        backup = asyncio.run(reset_airtable(Path(args.backup_dir)))
        asyncio.run(project_baseline())
        print(f"Airtable snapshot: {backup}")
        print("Airtable application tables reset and baseline projection synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
