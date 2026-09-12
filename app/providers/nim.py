import asyncio
from typing import Any

import httpx

from app.core.config import settings


class NIMProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class NIMClient:
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.1,
        max_tokens: int = 500,
    ) -> dict[str, Any]:
        if not settings.nvidia_nim_api_key or settings.nvidia_nim_api_key == "replace_me":
            raise NIMProviderError("NOT_CONFIGURED", "NVIDIA NIM is not configured")

        payload: dict[str, Any] = {
            "model": settings.nvidia_nim_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {settings.nvidia_nim_api_key}",
            "Content-Type": "application/json",
        }
        attempts = settings.nvidia_nim_max_retries + 1
        async with httpx.AsyncClient(timeout=settings.nvidia_nim_timeout_seconds) as client:
            for attempt in range(attempts):
                try:
                    response = await client.post(
                        f"{settings.nvidia_nim_base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                except httpx.TimeoutException as exc:
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0.25 * (2**attempt))
                        continue
                    raise NIMProviderError("TIMEOUT", "NVIDIA NIM timed out", retryable=True) from exc
                except httpx.RequestError as exc:
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0.25 * (2**attempt))
                        continue
                    raise NIMProviderError("NETWORK_ERROR", "NVIDIA NIM request failed", retryable=True) from exc

                if response.status_code in {408, 429, 500, 502, 503, 504} and attempt + 1 < attempts:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                if response.status_code >= 400:
                    raise NIMProviderError(
                        f"HTTP_{response.status_code}",
                        "NVIDIA NIM rejected the request",
                        retryable=response.status_code in {408, 429, 500, 502, 503, 504},
                    )
                try:
                    body = response.json()
                except ValueError as exc:
                    raise NIMProviderError("INVALID_JSON", "NVIDIA NIM returned invalid JSON") from exc
                if not isinstance(body.get("choices"), list) or not body["choices"]:
                    raise NIMProviderError("MALFORMED_RESPONSE", "NVIDIA NIM returned no choices")
                return body

        raise NIMProviderError("UNKNOWN", "NVIDIA NIM request failed")
