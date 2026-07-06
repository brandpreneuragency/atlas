from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

# A network-free stand-in for HermesClient (MASTER_PLAN §10).  Used by unit
# tests and dry-run mode.  Method names and signatures MUST mirror
# ``app.hermes.client.HermesClient`` — see ``test_mock_matches_interface``.


class MockHermes:
    def __init__(self, base_url: str = "", api_key: str = "", timeout_s: float = 10.0) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_s = timeout_s
        self._run_counter = 0
        self._sessions: dict[str, list[dict[str, Any]]] = {}

    async def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "platform": "hermes-agent",
            "gateway_state": "running",
            "active_agents": 0,
        }

    async def capabilities(self) -> dict[str, Any]:
        return {
            "features": {
                "run_submission": True,
                "run_events_sse": True,
                "session_chat_streaming": True,
            }
        }

    async def create_run(self, prompt: str, *, session_key: str | None = None) -> str:
        self._run_counter += 1
        run_id = f"mock-run-{self._run_counter}"
        # remember the prompt so run_events/run_status can echo it
        self._sessions[run_id] = [{"prompt": prompt}]
        return run_id

    async def run_status(self, run_id: str) -> dict[str, Any]:
        prompt = self._prompt_for(run_id)
        return {
            "status": "completed",
            "output_text": f"MOCK OUTPUT for: {prompt[:40]}",
            "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        }

    async def stop_run(self, run_id: str) -> None:
        # no-op for the mock
        return None

    async def approve_run(self, run_id: str, approval_id: str, decision: str) -> None:
        # no-op for the mock
        return None

    async def run_events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        prompt = self._prompt_for(run_id)
        yield {"type": "run.started", "run_id": run_id}
        yield {"type": "tool_progress", "summary": "mock tool"}
        yield {
            "type": "run.completed",
            "run_id": run_id,
            "output_text": f"MOCK OUTPUT for: {prompt[:40]}",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }

    async def sessions(
        self, q: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": "mock-session-1",
                "title": "Mock session",
                "updated_at": 0,
                "source": "chat",
            }
        ][:limit]

    async def session_messages(self, sid: str) -> list[dict[str, Any]]:
        return [
            {"role": "user", "content": "Reply PONG"},
            {"role": "assistant", "content": "PONG"},
        ]

    async def create_session(self) -> str:
        return f"mock-session-{len(self._sessions) + 1}"

    async def chat_stream(self, sid: str, message: str) -> AsyncIterator[str]:
        # Echo the user message back in three chunks so the UI can show
        # progressive token streaming.
        for chunk in [message[:3], message[3:7], message[7:]]:
            if chunk:
                yield chunk

    def _prompt_for(self, run_id: str) -> str:
        history = self._sessions.get(run_id)
        if history and isinstance(history[0], dict):
            return str(history[0].get("prompt", ""))
        return ""