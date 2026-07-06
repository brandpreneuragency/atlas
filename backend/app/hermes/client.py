from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.hermes.schemas import HermesUnavailable

# Per MASTER_PLAN §8 / Phase-0 records: terminal run lifecycle events.
_TERMINAL_RUN_EVENTS = {"run.completed", "run.failed", "run.cancelled"}


def _parse_sse_frame(frame: str) -> dict[str, Any] | None:
    """Parse one SSE frame (the text between two ``\\n\\n`` separators).

    - Comment/heartbeat lines (starting with ``:``) are ignored.
    - Only ``data:`` lines are collected; the payload is JSON-parsed.
    - Returns ``None`` for comment-only / empty / non-JSON frames.
    """
    data_lines: list[str] = []
    for line in frame.split("\n"):
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip(" "))
        # event:/id:/retry: fields are ignored by our consumers
    if not data_lines:
        return None
    raw = "\n".join(data_lines)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _sse_event_name(frame: str) -> str | None:
    """Return the ``event:`` field of an SSE frame, or ``None`` if absent."""
    for line in frame.split("\n"):
        if line.startswith("event:"):
            return line[len("event:"):].strip()
    return None


def _unwrap_list(data: Any, what: str) -> list[dict[str, Any]]:
    """Accept a bare JSON list or the live envelope ``{"object":"list","data":[...]}``."""
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        data = data["data"]
    if not isinstance(data, list):
        raise HermesUnavailable(f"{what} returned non-list JSON")
    return [item for item in data if isinstance(item, dict)]


class HermesClient:
    """Adapter for the Hermes runs API (:8642), MASTER_PLAN §7.

    Bearer auth = ``ATLAS_HERMES_API_KEY``. 10s default timeout for control
    calls; ``run_events`` / ``chat_stream`` use a streaming client with no
    overall timeout.
    """

    def __init__(self, base_url: str, api_key: str, timeout_s: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
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

    async def create_run(
        self, prompt: str, *, session_key: str | None = None
    ) -> str:
        payload: dict[str, Any] = {"input": prompt}
        if session_key is not None:
            payload["session_key"] = session_key
        data = await self._request("POST", "/v1/runs", json=payload)
        run_id = data.get("run_id")
        if not isinstance(run_id, str):
            raise HermesUnavailable(f"create_run returned no run_id: {data!r}")
        return run_id

    async def run_status(self, run_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/runs/{run_id}")

    async def stop_run(self, run_id: str) -> None:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout_s, headers=headers
            ) as client:
                response = await client.post(f"/v1/runs/{run_id}/stop")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc

    async def approve_run(
        self, run_id: str, approval_id: str, decision: str
    ) -> None:
        # Live contract (2026-07-06): body is {"choice": once|session|always|deny}.
        # approval_id is not part of the API (kept in the signature per §7 and
        # for MockHermes parity). Our decisions map: approved→once, rejected→deny.
        choice = {"approved": "once", "rejected": "deny"}.get(decision, decision)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout_s, headers=headers
            ) as client:
                response = await client.post(
                    f"/v1/runs/{run_id}/approval",
                    json={"choice": choice},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc

    async def run_events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        """Stream ``GET /v1/runs/{id}/events`` SSE lines into dicts.

        Per Phase-0 records: SSE uses ``data: {json}\\n\\n`` blocks, the event
        discriminator field is ``event`` (not ``type``); terminal events are
        ``run.completed`` / ``run.failed`` / ``run.cancelled``. Comments (lines
        starting with ``:``) and unknown event types are tolerated; unknown
        types are still yielded so callers can react.
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/v1/runs/{run_id}/events"
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    response.raise_for_status()
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        # SSE frames are separated by a blank line.
                        while "\n\n" in buffer:
                            frame, buffer = buffer.split("\n\n", 1)
                            event = _parse_sse_frame(frame)
                            if event is not None:
                                yield event
                                if event.get("event") in _TERMINAL_RUN_EVENTS:
                                    return
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc

    async def sessions(
        self, q: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if q is not None:
            params["q"] = q
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout_s, headers=headers
            ) as client:
                response = await client.get("/api/sessions", params=params)
                response.raise_for_status()
                return _unwrap_list(response.json(), "sessions")
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc

    async def session_messages(self, sid: str) -> list[dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout_s, headers=headers
            ) as client:
                response = await client.get(f"/api/sessions/{sid}/messages")
                response.raise_for_status()
                return _unwrap_list(response.json(), "session_messages")
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc

    async def create_session(self) -> str:
        # Live Hermes 400s on an empty body and nests the id under "session".
        data = await self._request("POST", "/api/sessions", json={})
        nested = data.get("session")
        if isinstance(nested, dict):
            data = nested
        sid = data.get("id")
        if not isinstance(sid, str):
            raise HermesUnavailable(f"create_session returned no id: {data!r}")
        return sid

    async def chat_stream(self, sid: str, message: str) -> AsyncIterator[str]:
        """Stream text tokens from ``POST /api/sessions/{sid}/chat/stream``.

        Live Hermes emits named SSE events; tokens arrive as
        ``event: assistant.delta`` / ``data: {"delta": "<chunk>"}``, the stream
        ends with ``event: done``, and ``event: error`` carries a message.
        The legacy ``data: {"token": "<chunk>"}`` shape is still accepted.
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/api/sessions/{sid}/chat/stream"
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", url, json={"message": message}, headers=headers
                ) as response:
                    response.raise_for_status()
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            frame, buffer = buffer.split("\n\n", 1)
                            name = _sse_event_name(frame)
                            payload = _parse_sse_frame(frame)
                            if name == "done":
                                return
                            if name == "error":
                                detail = "chat stream error"
                                if payload is not None and isinstance(
                                    payload.get("message"), str
                                ):
                                    detail = payload["message"]
                                raise HermesUnavailable(detail)
                            if payload is None:
                                continue
                            if name == "assistant.delta":
                                delta = payload.get("delta")
                                if isinstance(delta, str):
                                    yield delta
                            elif name is None:
                                token = payload.get("token")
                                if isinstance(token, str):
                                    yield token
        except httpx.HTTPError as exc:
            raise HermesUnavailable(str(exc)) from exc