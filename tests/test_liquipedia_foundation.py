from __future__ import annotations

import httpx
import pytest
from _pytest.monkeypatch import MonkeyPatch

from app.config import Settings
from app.providers.liquipedia.base import LiquipediaAccessRequiredError, LiquipediaHttpClient
from app.providers.liquipedia.cs2_provider import LiquipediaCS2Provider
from app.providers.liquipedia.dota2_provider import LiquipediaDota2Provider
from app.providers.liquipedia.models import LiquipediaClientSettings


def test_liquipedia_settings_use_contact_user_agent_and_enforce_minimum_interval(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("PANDASCORE_API_KEY", "pandascore-test-token")
    monkeypatch.setenv("LIQUIPEDIA_USER_AGENT", "CS2-Dota-Telegram-Bot/1.0 (contact: security@example.invalid)")
    monkeypatch.setenv("LIQUIPEDIA_MIN_REQUEST_INTERVAL_SECONDS", "2")

    settings = Settings()

    assert settings.liquipedia_user_agent.endswith("security@example.invalid)")
    assert settings.liquipedia_min_request_interval_seconds == 2


def test_liquipedia_settings_reject_interval_below_terms(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("PANDASCORE_API_KEY", "pandascore-test-token")
    monkeypatch.setenv("LIQUIPEDIA_MIN_REQUEST_INTERVAL_SECONDS", "1")

    with pytest.raises(ValueError, match="at least 2 seconds"):
        Settings()


async def test_liquipedia_client_sets_headers_and_caches_successful_responses() -> None:
    request_count = 0

    def response_handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert request.headers["User-Agent"] == "CS2-Dota-Telegram-Bot/1.0 (contact: security@example.invalid)"
        assert request.headers["Accept-Encoding"] == "gzip"
        return httpx.Response(200, json={"ok": True})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(response_handler))
    client = LiquipediaHttpClient(
        LiquipediaClientSettings(
            user_agent="CS2-Dota-Telegram-Bot/1.0 (contact: security@example.invalid)",
            cache_ttl_seconds=300,
            minimum_request_interval_seconds=2,
        ),
        client=http_client,
    )

    assert await client.get_json("https://example.test/documented-endpoint") == {"ok": True}
    assert await client.get_json("https://example.test/documented-endpoint") == {"ok": True}

    assert request_count == 1
    await http_client.aclose()


async def test_liquipedia_providers_require_approved_documentation() -> None:
    http_client = httpx.AsyncClient()
    client = LiquipediaHttpClient(
        LiquipediaClientSettings(
            user_agent="CS2-Dota-Telegram-Bot/1.0 (contact: security@example.invalid)",
            cache_ttl_seconds=300,
            minimum_request_interval_seconds=2,
        ),
        client=http_client,
    )

    with pytest.raises(LiquipediaAccessRequiredError, match="LiquipediaDB access"):
        await LiquipediaCS2Provider(client).get_recent_finished_matches()
    with pytest.raises(LiquipediaAccessRequiredError, match="LiquipediaDB access"):
        await LiquipediaDota2Provider(client).get_recent_finished_matches()

    await http_client.aclose()
