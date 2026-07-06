from __future__ import annotations

from app.config import Settings
from app.engine.mock import MockHermes
from app.hermes.client import HermesClient
from app.hermes.schemas import HermesUnavailable

# Adapter factory helpers shared by routers. When ``ATLAS_MOCK_HERMES=1`` the
# runs-side adapter is the in-process MockHermes (MASTER_PLAN §10); otherwise a
# real HermesClient. The admin adapter has no mock — callers must guard with
# ``settings.mock_hermes``.


def make_hermes_client(settings: Settings, *, timeout_s: float = 10.0) -> HermesClient | MockHermes:
    if settings.mock_hermes:
        return MockHermes(settings.hermes_runs_url, settings.hermes_api_key, timeout_s)
    return HermesClient(settings.hermes_runs_url, settings.hermes_api_key, timeout_s)


__all__ = ["HermesClient", "HermesUnavailable", "MockHermes", "make_hermes_client"]