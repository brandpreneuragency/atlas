import json
from pathlib import Path

import httpx
import pytest
import respx

from app.hermes.admin import HermesAdmin
from app.hermes.schemas import HermesUnavailable

_ADMIN = "http://hermes:9119"


def _index_html() -> str:
    return Path("tests/fixtures/dashboard_index.html").read_text()


def _fixture() -> dict:
    return json.loads(Path("tests/fixtures/hermes-contract.json").read_text())


# --- _token ----------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_token_extracts_using_pinned_regex():
    respx.get(f"{_ADMIN}/").mock(
        return_value=httpx.Response(200, text=_index_html())
    )
    admin = HermesAdmin(_ADMIN)
    token = await admin._token()
    assert token == "FAKE_TOKEN_0123456789abcdefghij"


@pytest.mark.asyncio
@respx.mock
async def test_token_is_cached_across_calls():
    route = respx.get(f"{_ADMIN}/").mock(
        return_value=httpx.Response(200, text=_index_html())
    )
    admin = HermesAdmin(_ADMIN)
    first = await admin._token()
    second = await admin._token()
    assert first == second
    # index HTML fetched exactly once → token cached.
    assert route.call_count == 1


# --- cron_jobs ------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_cron_jobs_sends_bearer_and_parses_bare_array():
    respx.get(f"{_ADMIN}/").mock(
        return_value=httpx.Response(200, text=_index_html())
    )
    jobs_payload = _fixture()["cron_jobs_list_example"]
    route = respx.get(f"{_ADMIN}/api/cron/jobs").mock(
        return_value=httpx.Response(200, json=jobs_payload)
    )
    jobs = await HermesAdmin(_ADMIN).cron_jobs()
    assert jobs == jobs_payload
    assert route.called
    # recorded auth header
    assert (
        route.calls.last.request.headers["Authorization"]
        == "Bearer FAKE_TOKEN_0123456789abcdefghij"
    )


# --- 401 → re-scrape + single retry --------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_cron_jobs_re_scrapes_token_on_401_then_retries_once():
    # first token scrape
    index = respx.get(f"{_ADMIN}/").mock(
        return_value=httpx.Response(200, text=_index_html())
    )
    # first cron call → 401 (token stale)
    stale = respx.get(f"{_ADMIN}/api/cron/jobs").mock(
        side_effect=[
            httpx.Response(401, json={"detail": "unauthorized"}),
            httpx.Response(200, json=_fixture()["cron_jobs_list_example"]),
        ]
    )
    jobs = await HermesAdmin(_ADMIN).cron_jobs()
    assert isinstance(jobs, list)
    # token scraped at least twice, cron hit twice
    assert index.call_count == 2
    assert stale.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_cron_jobs_does_not_retry_twice_on_persistent_401():
    respx.get(f"{_ADMIN}/").mock(
        return_value=httpx.Response(200, text=_index_html())
    )
    respx.get(f"{_ADMIN}/api/cron/jobs").mock(
        return_value=httpx.Response(401, json={"detail": "unauthorized"})
    )
    with pytest.raises(HermesUnavailable):
        await HermesAdmin(_ADMIN).cron_jobs()


# --- env_list returns masked entries untouched ----------------------------


@pytest.mark.asyncio
@respx.mock
async def test_env_list_returns_masked_entries_untouched():
    respx.get(f"{_ADMIN}/").mock(
        return_value=httpx.Response(200, text=_index_html())
    )
    env_payload = _fixture()["env_masked_example"]
    respx.get(f"{_ADMIN}/api/env").mock(
        return_value=httpx.Response(200, json=env_payload)
    )
    env = await HermesAdmin(_ADMIN).env_list()
    assert env == env_payload  # dict keyed by var name, masked values preserved
    # specifically the masked redacted_value is not decoded/modified
    assert env["OPENROUTER_API_KEY"]["redacted_value"] == "sk-o...61b8"


# --- live contract shapes (verified against running Hermes 2026-07-06) ----


@pytest.mark.asyncio
@respx.mock
async def test_model_set_sends_scope_main():
    respx.get(f"{_ADMIN}/").mock(
        return_value=httpx.Response(200, text=_index_html())
    )
    route = respx.post(f"{_ADMIN}/api/model/set").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await HermesAdmin(_ADMIN).model_set("deepseek/deepseek-v4-flash", "nous")
    import json as _json

    body = _json.loads(route.calls.last.request.content)
    assert body == {
        "scope": "main",
        "model": "deepseek/deepseek-v4-flash",
        "provider": "nous",
    }


@pytest.mark.asyncio
@respx.mock
async def test_env_delete_uses_body_not_path():
    respx.get(f"{_ADMIN}/").mock(
        return_value=httpx.Response(200, text=_index_html())
    )
    route = respx.delete(f"{_ADMIN}/api/env").mock(
        return_value=httpx.Response(200, json={"ok": True, "key": "FAKE_KEY"})
    )
    result = await HermesAdmin(_ADMIN).env_delete("FAKE_KEY")
    assert result["ok"] is True
    import json as _json

    body = _json.loads(route.calls.last.request.content)
    assert body == {"key": "FAKE_KEY"}


# --- connect error ---------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_admin_connect_error_raises_unavailable():
    respx.get(f"{_ADMIN}/").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(HermesUnavailable):
        await HermesAdmin(_ADMIN).cron_jobs()