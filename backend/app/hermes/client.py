from __future__ import annotations

from typing import Any

import httpx

from app.hermes.schemas import HermesUnavailable


class HermesClient:
    def __init__(self, base_url: str, api_key: str, timeout_s: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout_s, headers=headers
            ) as client:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise HermesUnavailable("Hermes returned non-object JSON")
                return data
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health/detailed")

    async def capabilities(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/capabilities")
