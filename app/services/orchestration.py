from urllib.parse import urlsplit

from app.core.config import settings

DIRECT_ROUTES = {
    "inbound": {"transport": "direct", "url": "/api/channels/inbound", "workflow_id": None},
    "appointment": {"transport": "direct", "url": "/api/appointments", "workflow_id": None},
}
N8N_WORKFLOW_IDS = {
    "inbound": "coa-inbound-channel",
    "appointment": "coa-appointment-confirm",
}


def _safe_webhook_url(value: str) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return None
    return value.rstrip("/")


def _ui_origin(explicit_url: str, webhook_urls: list[str]) -> str | None:
    candidates = [explicit_url, *webhook_urls]
    for candidate in candidates:
        safe_url = _safe_webhook_url(candidate)
        if safe_url:
            parsed = urlsplit(safe_url)
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


def demo_orchestration_config() -> dict:
    requested_mode = settings.orchestration_mode
    routes = {name: dict(route) for name, route in DIRECT_ROUTES.items()}
    missing: list[str] = []
    safe_webhooks: list[str] = []

    if requested_mode == "n8n":
        configured = {
            "inbound": _safe_webhook_url(settings.n8n_inbound_webhook_url),
            "appointment": _safe_webhook_url(settings.n8n_appointment_webhook_url),
        }
        for name, webhook_url in configured.items():
            if webhook_url:
                routes[name] = {
                    "transport": "n8n",
                    "url": webhook_url,
                    "workflow_id": N8N_WORKFLOW_IDS[name],
                }
                safe_webhooks.append(webhook_url)
            else:
                missing.append(name)

    active_transports = {route["transport"] for route in routes.values()}
    if requested_mode == "direct":
        status = "ready"
    elif active_transports == {"n8n"}:
        status = "ready"
    else:
        status = "degraded"

    return {
        "requested_mode": requested_mode,
        "status": status,
        "routes": routes,
        "n8n_ui_base_url": _ui_origin(settings.n8n_ui_base_url, safe_webhooks),
        "fallback_routes": missing,
        "flow": [
            "Browser demo",
            "n8n",
            "FastAPI control layer",
            "NIM / PostgreSQL / Airtable",
            "n8n",
            "Browser demo",
        ]
        if requested_mode == "n8n"
        else ["Browser demo", "FastAPI control layer", "NIM / PostgreSQL / Airtable", "Browser demo"],
        "boundary": "NVIDIA NIM and deterministic policy remain inside the Python control layer.",
    }
