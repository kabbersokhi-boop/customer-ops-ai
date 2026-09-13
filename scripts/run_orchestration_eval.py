#!/usr/bin/env python3
import argparse
import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

import httpx


def _absolute_url(api_base_url: str, route_url: str) -> str:
    return route_url if route_url.startswith(("http://", "https://")) else urljoin(api_base_url, route_url)


def _assert_n8n_trace(body: dict, expected_workflow_id: str) -> str:
    trace = body.get("orchestration") or {}
    assert trace.get("mode") == "n8n", "response did not traverse n8n"
    assert trace.get("workflow_id") == expected_workflow_id, "unexpected workflow executed"
    execution_id = str(trace.get("execution_id") or "")
    assert execution_id, "n8n execution ID is missing"
    return execution_id


async def run(api_base_url: str) -> int:
    api_base_url = api_base_url.rstrip("/") + "/"
    timeout = httpx.Timeout(120.0, connect=10.0)
    token = secrets.token_hex(6)
    async with httpx.AsyncClient(timeout=timeout) as client:
        config_response = await client.get(urljoin(api_base_url, "api/demo/config"))
        config_response.raise_for_status()
        config = config_response.json()
        assert config.get("status") == "ready", "orchestration configuration is degraded"
        inbound_route = config["routes"]["inbound"]
        appointment_route = config["routes"]["appointment"]
        assert inbound_route["transport"] == "n8n", "inbound route is not n8n"
        assert appointment_route["transport"] == "n8n", "appointment route is not n8n"

        inbound_payload = {
            "event_id": f"orchestration-eval-{token}",
            "channel": "browser-demo-eval",
            "customer_name": "Synthetic Eval Customer",
            "customer_phone": f"synthetic-{token}",
            "text": (
                "I want a white Fortuner automatic under 45 lakh, this month, "
                "and I have a Creta to exchange. Can I book a test drive?"
            ),
            "metadata": {"synthetic_eval": True},
        }
        inbound_response = await client.post(_absolute_url(api_base_url, inbound_route["url"]), json=inbound_payload)
        inbound_response.raise_for_status()
        inbound = inbound_response.json()
        inbound_execution = _assert_n8n_trace(inbound, inbound_route["workflow_id"])
        assert inbound.get("lead", {}).get("id"), "control layer did not return a lead"
        assert isinstance(inbound.get("inventory_matches"), list), "inventory result was not validated"

        inbound_replay_response = await client.post(
            _absolute_url(api_base_url, inbound_route["url"]),
            json=inbound_payload,
        )
        inbound_replay_response.raise_for_status()
        inbound_replay = inbound_replay_response.json()
        inbound_replay_execution = _assert_n8n_trace(inbound_replay, inbound_route["workflow_id"])
        assert inbound_replay.get("idempotency", {}).get("replayed") is True, "inbound replay was not detected"
        assert inbound_replay["lead"]["id"] == inbound["lead"]["id"], "inbound replay created another lead"

        appointment_payload = {
            "lead_id": inbound["lead"]["id"],
            "kind": "test_drive",
            "branch": "Gurugram",
            "scheduled_for": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "idempotency_key": f"orchestration-booking-{token}",
            "stock_id": (inbound.get("inventory_matches") or [{}])[0].get("stock_id"),
        }
        appointment_url = _absolute_url(api_base_url, appointment_route["url"])
        first_response = await client.post(appointment_url, json=appointment_payload)
        first_response.raise_for_status()
        first = first_response.json()
        first_execution = _assert_n8n_trace(first, appointment_route["workflow_id"])
        assert first.get("created") is True, "first appointment command did not create a booking"

        replay_response = await client.post(appointment_url, json=appointment_payload)
        replay_response.raise_for_status()
        replay = replay_response.json()
        replay_execution = _assert_n8n_trace(replay, appointment_route["workflow_id"])
        assert replay.get("created") is False, "booking replay was not deduplicated"
        assert replay.get("appointment_id") == first.get("appointment_id"), "replay returned a different booking"

        appointments_response = await client.get(urljoin(api_base_url, "api/ops/appointments?limit=100"))
        appointments_response.raise_for_status()
        booking_count = sum(
            row.get("id") == first["appointment_id"] for row in appointments_response.json()
        )
        assert booking_count == 1, "durable appointment count is not one"

    print("Orchestration eval: PASS")
    print(f"  inbound n8n executions: {inbound_execution}, {inbound_replay_execution}")
    print(f"  appointment executions: {first_execution}, {replay_execution}")
    print("  durable booking count: 1")
    print("  NIM/database/CRM policy boundary: FastAPI control layer")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the live n8n-first demo path without printing records.")
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.api_base_url))
    except (AssertionError, httpx.HTTPError) as exc:
        print(f"Orchestration eval: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
