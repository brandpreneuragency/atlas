import json
import inspect
from pathlib import Path

import httpx
import pytest
import respx

from app.engine.mock import MockHermes
from app.hermes.client import HermesClient
from app.hermes.schemas import HermesUnavailable


def _fixture() -> dict:
    return json.loads(Path("tests/fixtures/hermes-contract.json").read_text())


def _run_sample_sse() -> str:
    return Path("tests/fixtures/hermes-run-sample.txt").read_text()


# --- create_run -------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_create_run_posts_recorded_payload_and_returns_run_id():
    respx.post("http://hermes:8642/v1/runs").mock(
        return_value=httpx.Response(
            202, json={"run_id": "run_deadbeef", "status": "started"}
        )
    )

    run_id = await HermesClient("http://hermes:8642", "testkey").create_run(
        "Reply PONG", session_key="sess-1"
    )

    assert run_id == "run_deadbeef"
    request = respx.calls.last.request
    body = json.loads(request.content)
    assert body == {"input": "Reply PONG", "session_key": "sess-1"}
    assert request.headers["Authorization"] == "Bearer testkey"


# --- run_events ------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_run_events_parses_sse_and_ends_on_terminal():
    respx.get("http://hermes:8642/v1/runs/run_deadbeef/events").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_run_sample_sse(),
        )
    )

    events = []
    async for ev in HermesClient("http://hermes:8642", "testkey").run_events(
        "run_deadbeef"
    ):
        events.append(ev)

    assert [e["event"] for e in events] == [
        "tool.started",
        "tool.completed",
        "reasoning.available",
        "run.completed",
    ]
    terminal = events[-1]
    assert terminal["event"] == "run.completed"
    assert terminal["output"] == "PONG"
    assert terminal["usage"] == {
        "input_tokens": 120,
        "output_tokens": 3,
        "total_tokens": 123,
    }


# --- stop_run / approve_run ------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_stop_run_hits_right_path():
    route = respx.post(
        "http://hermes:8642/v1/runs/run_deadbeef/stop"
    ).mock(return_value=httpx.Response(204))
    await HermesClient("http://hermes:8642", "testkey").stop_run("run_deadbeef")
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_approve_run_hits_right_path():
    route = respx.post(
        "http://hermes:8642/v1/runs/run_deadbeef/approval"
    ).mock(return_value=httpx.Response(204))
    await HermesClient("http://hermes:8642", "testkey").approve_run(
        "run_deadbeef", "appr-1", "approved"
    )
    assert route.called
    body = json.loads(respx.calls.last.request.content)
    # live contract (verified 2026-07-06): {"choice": once|session|always|deny};
    # approved → once, rejected → deny. approval_id is not part of the API.
    assert body == {"choice": "once"}


@pytest.mark.asyncio
@respx.mock
async def test_approve_run_rejected_maps_to_deny():
    respx.post("http://hermes:8642/v1/runs/run_deadbeef/approval").mock(
        return_value=httpx.Response(204)
    )
    await HermesClient("http://hermes:8642", "testkey").approve_run(
        "run_deadbeef", "", "rejected"
    )
    body = json.loads(respx.calls.last.request.content)
    assert body == {"choice": "deny"}


# --- run_status ------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_run_status_returns_status_dict():
    payload = _fixture()["run_status_completed_example"]
    respx.get("http://hermes:8642/v1/runs/run_deadbeef").mock(
        return_value=httpx.Response(200, json=payload)
    )
    result = await HermesClient("http://hermes:8642", "testkey").run_status(
        "run_deadbeef"
    )
    assert result["status"] == "completed"
    assert result["output"] == "PONG"
    assert result["usage"]["total_tokens"] == 123


# --- sessions / session_messages / create_session --------------------------


@pytest.mark.asyncio
@respx.mock
async def test_sessions_returns_list():
    respx.get("http://hermes:8642/api/sessions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "sess-1",
                    "title": "first message",
                    "updated_at": 1783300012,
                    "source": "chat",
                }
            ],
        )
    )
    sessions = await HermesClient("http://hermes:8642", "testkey").sessions()
    assert len(sessions) == 1
    assert sessions[0]["id"] == "sess-1"


@pytest.mark.asyncio
@respx.mock
async def test_sessions_unwraps_live_envelope():
    # Live Hermes wraps the list: {"object": "list", "data": [...]}
    respx.get("http://hermes:8642/api/sessions").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {
                        "id": "20260701_071709_13bb4b",
                        "source": "tui",
                        "model": "gpt-5.5",
                        "title": "VS Code Swarm Models Tools Refactor Pack #3",
                        "message_count": 291,
                    }
                ],
            },
        )
    )
    sessions = await HermesClient("http://hermes:8642", "testkey").sessions()
    assert len(sessions) == 1
    assert sessions[0]["id"] == "20260701_071709_13bb4b"


@pytest.mark.asyncio
@respx.mock
async def test_session_messages_unwraps_live_envelope():
    respx.get("http://hermes:8642/api/sessions/sess-1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "session_id": "sess-1",
                "data": [
                    {"role": "user", "content": "Reply PONG"},
                    {"role": "assistant", "content": "PONG"},
                ],
            },
        )
    )
    msgs = await HermesClient("http://hermes:8642", "testkey").session_messages(
        "sess-1"
    )
    assert [m["role"] for m in msgs] == ["user", "assistant"]


@pytest.mark.asyncio
@respx.mock
async def test_sessions_passes_q_and_limit():
    route = respx.get(url__regex=r".*/api/sessions.*").mock(
        return_value=httpx.Response(200, json=[])
    )
    await HermesClient("http://hermes:8642", "testkey").sessions(q="ping", limit=7)
    assert route.called
    request = respx.calls.last.request
    assert "q=ping" in str(request.url)
    assert "limit=7" in str(request.url)


@pytest.mark.asyncio
@respx.mock
async def test_session_messages_returns_list():
    respx.get("http://hermes:8642/api/sessions/sess-1/messages").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"role": "user", "content": "Reply PONG"},
                {"role": "assistant", "content": "PONG"},
            ],
        )
    )
    msgs = await HermesClient("http://hermes:8642", "testkey").session_messages(
        "sess-1"
    )
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "PONG"


@pytest.mark.asyncio
@respx.mock
async def test_create_session_returns_id():
    respx.post("http://hermes:8642/api/sessions").mock(
        return_value=httpx.Response(201, json={"id": "sess-new"})
    )
    sid = await HermesClient("http://hermes:8642", "testkey").create_session()
    assert sid == "sess-new"


@pytest.mark.asyncio
@respx.mock
async def test_create_session_live_shape():
    # Live Hermes: requires a JSON body and nests the id under "session".
    route = respx.post("http://hermes:8642/api/sessions").mock(
        return_value=httpx.Response(
            201,
            json={
                "object": "hermes.session",
                "session": {"id": "api_1783314642_297e0408", "source": "api_server"},
            },
        )
    )
    sid = await HermesClient("http://hermes:8642", "testkey").create_session()
    assert sid == "api_1783314642_297e0408"
    assert route.calls.last.request.content == b"{}"


# --- chat_stream -----------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_chat_stream_yields_text_chunks():
    sse = (
        'data: {"token":"Hello"}\n\n'
        'data: {"token":" world"}\n\n'
        'data: {"token":"."}\n\n'
        'data: [DONE]\n\n'
    )
    respx.post(
        "http://hermes:8642/api/sessions/sess-1/chat/stream"
    ).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse,
        )
    )

    chunks = []
    async for chunk in HermesClient("http://hermes:8642", "testkey").chat_stream(
        "sess-1", "Reply PONG"
    ):
        chunks.append(chunk)

    assert chunks == ["Hello", " world", "."]
    # request body carries the message
    body = json.loads(respx.calls.last.request.content)
    assert body == {"message": "Reply PONG"}


@pytest.mark.asyncio
@respx.mock
async def test_chat_stream_yields_live_assistant_deltas():
    # Live Hermes emits named SSE events; only assistant.delta carries tokens.
    sse = (
        'event: run.started\n'
        'data: {"user_message":{"role":"user","content":"Reply PONG"},"session_id":"s","run_id":"r","seq":1,"ts":1.0}\n\n'
        'event: message.started\n'
        'data: {"message":{"id":"msg_1","role":"assistant"},"seq":2,"ts":1.0}\n\n'
        'event: tool.progress\n'
        'data: {"message_id":"msg_1","tool_name":"_thinking","delta":"NOT-A-TOKEN","seq":3,"ts":1.0}\n\n'
        'event: assistant.delta\n'
        'data: {"message_id":"msg_1","delta":"PO","seq":4,"ts":1.0}\n\n'
        'event: assistant.delta\n'
        'data: {"message_id":"msg_1","delta":"NG","seq":5,"ts":1.0}\n\n'
        'event: assistant.completed\n'
        'data: {"message_id":"msg_1","content":"PONG","completed":true,"seq":6,"ts":1.0}\n\n'
        'event: done\n'
        'data: {"session_id":"s","run_id":"r","seq":7,"ts":1.0}\n\n'
    )
    respx.post("http://hermes:8642/api/sessions/sess-1/chat/stream").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse
        )
    )
    chunks = [
        c
        async for c in HermesClient("http://hermes:8642", "testkey").chat_stream(
            "sess-1", "Reply PONG"
        )
    ]
    assert chunks == ["PO", "NG"]


@pytest.mark.asyncio
@respx.mock
async def test_chat_stream_raises_on_error_event():
    sse = (
        'event: error\n'
        'data: {"message":"No access token found","seq":1,"ts":1.0}\n\n'
        'event: done\n'
        'data: {"seq":2,"ts":1.0}\n\n'
    )
    respx.post("http://hermes:8642/api/sessions/sess-1/chat/stream").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse
        )
    )
    with pytest.raises(HermesUnavailable, match="No access token"):
        async for _ in HermesClient("http://hermes:8642", "testkey").chat_stream(
            "sess-1", "hi"
        ):
            pass


# --- MockHermes mirrors HermesClient interface ----------------------------


def test_mock_matches_interface():
    real_methods = {
        n for n, _ in inspect.getmembers(HermesClient, predicate=inspect.isfunction)
    }
    real_methods.discard("_request")
    mock_methods = {
        n for n, _ in inspect.getmembers(MockHermes, predicate=inspect.isfunction)
    }
    mock_methods.discard("_request")

    missing = real_methods - mock_methods
    assert not missing, f"MockHermes missing: {sorted(missing)}"
    # MockHermes may add helpers but must not drop any HermesClient method.
    assert not (mock_methods - real_methods - {"_prompt_for"})

    # signature parity on shared public methods
    for name in sorted(real_methods & mock_methods):
        if name.startswith("__"):
            continue
        real_sig = inspect.signature(getattr(HermesClient, name))
        mock_sig = inspect.signature(getattr(MockHermes, name))
        assert real_sig == mock_sig, f"signature drift on {name}: {real_sig} vs {mock_sig}"


@pytest.mark.asyncio
async def test_mock_run_events_contract_per_section_10():
    mock = MockHermes("http://hermes:8642", "ignored")
    run_id = await mock.create_run("Reply PONG")
    assert run_id.startswith("mock-run-")

    events = [ev async for ev in mock.run_events(run_id)]
    assert events[0]["type"] == "run.started"
    assert events[1]["type"] == "tool_progress"
    assert events[1]["summary"] == "mock tool"
    terminal = events[-1]
    assert terminal["type"] == "run.completed"
    assert "Reply PONG" in terminal["output_text"]
    assert terminal["usage"] == {
        "input_tokens": 100,
        "output_tokens": 50,
    }


@pytest.mark.asyncio
async def test_mock_run_status_completed():
    mock = MockHermes("http://hermes:8642", "ignored")
    run_id = await mock.create_run("ping")
    status = await mock.run_status(run_id)
    assert status["status"] == "completed"
    assert "output_text" in status
    assert status["usage"]["input_tokens"] == 100