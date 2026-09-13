#!/usr/bin/env python3
import json
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

API_BASE_URL = "http://127.0.0.1:8000"
EXPECTED_BASELINE = {
    "inventory": 300,
    "customers": 60,
    "leads": 60,
    "interactions": 60,
    "appointments": 16,
    "pending_approvals": 5,
    "service_requests": 12,
}


class Preflight:
    def __init__(self) -> None:
        self.failed = False

    def report(self, label: str, passed: bool, detail: str) -> None:
        symbol = "PASS" if passed else "FAIL"
        print(f"[{symbol}] {label}: {detail}")
        self.failed = self.failed or not passed

    @staticmethod
    def json_get(url: str, timeout: float = 5) -> dict:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)

    @staticmethod
    def page_ok(path: str) -> bool:
        request = Request(f"{API_BASE_URL}{path}", headers={"Accept": "text/html"})
        with urlopen(request, timeout=5) as response:
            return response.status == 200 and "text/html" in response.headers.get("Content-Type", "")

    @staticmethod
    def options_ok(url: str) -> bool:
        request = Request(
            url,
            method="OPTIONS",
            headers={
                "Origin": API_BASE_URL,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        with urlopen(request, timeout=5) as response:
            return response.status in {200, 204}

    def wait_for_api(self) -> bool:
        for _ in range(30):
            try:
                if self.json_get(f"{API_BASE_URL}/ready", timeout=2).get("status") == "ready":
                    return True
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
                time.sleep(2)
        return False

    def docker(self) -> None:
        result = subprocess.run(
            ["docker", "compose", "ps", "--status", "running", "--services"],
            check=False,
            capture_output=True,
            text=True,
        )
        services = set(result.stdout.split())
        self.report("Docker stack", {"api", "postgres"}.issubset(services), f"running={','.join(sorted(services)) or 'none'}")

    def pages(self) -> None:
        for label, path in [("Customer demo", "/customer"), ("Operations console", "/")]:
            try:
                self.report(label, self.page_ok(path), f"{API_BASE_URL}{path}")
            except (HTTPError, URLError, TimeoutError, OSError):
                self.report(label, False, f"unreachable at {API_BASE_URL}{path}")

    def data(self) -> None:
        try:
            status = self.json_get(f"{API_BASE_URL}/api/demo/status")
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            self.report("Synthetic seed", False, "aggregate status endpoint unavailable")
            return
        counts = status.get("counts", {})
        missing = [name for name, minimum in EXPECTED_BASELINE.items() if counts.get(name, 0) < minimum]
        self.report(
            "Synthetic seed",
            status.get("synthetic") is True and not missing,
            "baseline present" if not missing else f"below baseline: {','.join(missing)}",
        )

    def orchestration(self) -> None:
        try:
            config = self.json_get(f"{API_BASE_URL}/api/demo/config")
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            self.report("Orchestration discovery", False, "configuration endpoint unavailable")
            return
        routes = config.get("routes", {})
        transports = {name: route.get("transport") for name, route in routes.items()}
        self.report("Orchestration discovery", config.get("status") == "ready", f"routes={transports}")
        if set(transports.values()) != {"n8n"}:
            print("[INFO] n8n execution visibility is not active; direct fallback remains usable.")
            return

        webhook_urls = [route.get("url", "") for route in routes.values()]
        origin = urlsplit(webhook_urls[0])
        n8n_health = f"{origin.scheme}://{origin.netloc}/healthz"
        try:
            with urlopen(n8n_health, timeout=5) as response:
                self.report("n8n runtime", response.status == 200, n8n_health)
        except (HTTPError, URLError, TimeoutError, OSError):
            self.report("n8n runtime", False, f"unreachable at {n8n_health}")
        for route_name, webhook_url in zip(routes, webhook_urls, strict=True):
            try:
                self.report(f"n8n {route_name} webhook", self.options_ok(webhook_url), "published and CORS-ready")
            except (HTTPError, URLError, TimeoutError, OSError):
                self.report(f"n8n {route_name} webhook", False, "preflight rejected or unreachable")

    def run(self) -> int:
        print("Customer Ops AI interview preflight (no credentials or records are printed)\n")
        self.docker()
        api_ready = self.wait_for_api()
        self.report("FastAPI + PostgreSQL readiness", api_ready, f"{API_BASE_URL}/ready")
        if api_ready:
            self.pages()
            self.data()
            self.orchestration()
        return 1 if self.failed else 0


if __name__ == "__main__":
    raise SystemExit(Preflight().run())
