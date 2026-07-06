from __future__ import annotations

import re
from typing import Any

import httpx

from app.hermes.schemas import HermesUnavailable

# PINNED (Phase-0, PROGRESS.md): injected token in 9119 dashboard index HTML.
# window.__HERMES_SESSION_TOKEN__="<token>"; — token rotates per Hermes reboot.
_TOKEN_REGEX = re.compile(r'__HERMES_SESSION_TOKEN__\s*=\s*"([A-Za-z0-9_-]+)"')


class HermesAdmin:
    """Adapter for the Hermes dashboard admin API (:9119), MASTER_PLAN §7.

    Protected routes require the ephemeral session token scraped from the
    index HTML and sent as ``Authorization: Bearer <token>``. The token is
    cached on this instance and re-scraped on a 401, with a single retry.
    """

    def __init__(self, base_url: str, timeout_s: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._cached_token: str | None = None

    async def _scrape_token(self) -> str:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout_s
            ) as client:
                response = await client.get("/")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc
        match = _TOKEN_REGEX.search(response.text)
        if match is None:
            raise HermesUnavailable("could not scrape session token from dashboard index")
        token = match.group(1)
        self._cached_token = token
        return token

    async def _token_value(self) -> str:
        if self._cached_token is None:
            await self._scrape_token()
        assert self._cached_token is not None
        return self._cached_token

    async def _token(self) -> str:
        """Public-ish accessor used by tests; returns the cached token."""
        return await self._token_value()

    async def _authed_request(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        """Authed request with single retry-on-401 (re-scrape token once)."""
        headers = kwargs.pop("headers", {})
        for _attempt in range(2):
            token = await self._token_value()
            headers = {**headers, "Authorization": f"Bearer {token}"}
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url, timeout=self.timeout_s
                ) as client:
                    response = await client.request(method, path, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                raise HermesUnavailable(str(exc)) from exc
            if response.status_code != 401:
                return response
            # token rejected → invalidate cache and retry once
            self._cached_token = None
        # second attempt also 401 → surface as unavailable (do not loop)
        raise HermesUnavailable(f"{method} {path} → 401 after token refresh")

    async def _authed_json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._authed_request(method, path, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc
        try:
            return response.json()
        except ValueError as exc:
            raise HermesUnavailable(f"non-JSON response from {path}") from exc

    # ---- cron ---------------------------------------------------------------

    async def cron_jobs(self) -> list[dict[str, Any]]:
        data = await self._authed_json("GET", "/api/cron/jobs")
        if not isinstance(data, list):
            raise HermesUnavailable("/api/cron/jobs returned non-list JSON")
        return [item for item in data if isinstance(item, dict)]

    async def cron_create(self, job: dict[str, Any]) -> dict[str, Any]:
        data = await self._authed_json("POST", "/api/cron/jobs", json=job)
        if not isinstance(data, dict):
            raise HermesUnavailable("cron_create returned non-object JSON")
        return data

    async def cron_update(self, job_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = await self._authed_json("PUT", f"/api/cron/jobs/{job_id}", json=patch)
        if not isinstance(data, dict):
            raise HermesUnavailable("cron_update returned non-object JSON")
        return data

    async def cron_pause(self, job_id: str) -> dict[str, Any]:
        return await self._cron_action(job_id, "pause")

    async def cron_resume(self, job_id: str) -> dict[str, Any]:
        return await self._cron_action(job_id, "resume")

    async def cron_trigger(self, job_id: str) -> dict[str, Any]:
        return await self._cron_action(job_id, "trigger")

    async def cron_delete(self, job_id: str) -> None:
        response = await self._authed_request("DELETE", f"/api/cron/jobs/{job_id}")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc

    async def _cron_action(self, job_id: str, action: str) -> dict[str, Any]:
        data = await self._authed_json("POST", f"/api/cron/jobs/{job_id}/{action}")
        if not isinstance(data, dict):
            raise HermesUnavailable(f"cron_{action} returned non-object JSON")
        return data

    # ---- model --------------------------------------------------------------

    async def model_info(self) -> dict[str, Any]:
        return self._require_dict(await self._authed_json("GET", "/api/model/info"))

    async def model_options(self) -> dict[str, Any]:
        return self._require_dict(await self._authed_json("GET", "/api/model/options"))

    async def model_set(self, model: str, provider: str) -> dict[str, Any]:
        # Live contract: scope is required; "main" writes the primary model slot.
        data = await self._authed_json(
            "POST",
            "/api/model/set",
            json={"scope": "main", "model": model, "provider": provider},
        )
        return self._require_dict(data)

    # ---- env ----------------------------------------------------------------

    async def env_list(self) -> dict[str, Any]:
        data = await self._authed_json("GET", "/api/env")
        if not isinstance(data, dict):
            raise HermesUnavailable("/api/env returned non-object JSON")
        return data

    async def env_put(self, key: str, value: str) -> dict[str, Any]:
        data = await self._authed_json("PUT", "/api/env", json={"key": key, "value": value})
        return self._require_dict(data)

    async def env_delete(self, key: str) -> dict[str, Any]:
        # Live contract: DELETE /api/env with {"key": ...} body (path form → 405).
        data = await self._authed_json("DELETE", "/api/env", json={"key": key})
        return self._require_dict(data)

    # ---- analytics / logs / gateway ----------------------------------------

    async def analytics_usage(self) -> dict[str, Any]:
        return self._require_dict(await self._authed_json("GET", "/api/analytics/usage"))

    async def analytics_models(self) -> dict[str, Any]:
        return self._require_dict(await self._authed_json("GET", "/api/analytics/models"))

    async def logs(self, tail: int = 200) -> str:
        response = await self._authed_request(
            "GET", "/api/logs", params={"tail": tail}
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc
        return response.text

    async def gateway_restart(self) -> None:
        response = await self._authed_request("POST", "/api/gateway/restart")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc

    @staticmethod
    def _require_dict(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise HermesUnavailable("Hermes returned non-object JSON")
        return data