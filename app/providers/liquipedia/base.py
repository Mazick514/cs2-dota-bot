from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.providers.base import DataProviderError, DataProviderRateLimitError, DataProviderTemporaryError
from app.providers.liquipedia.models import LiquipediaClientSettings

LOGGER = logging.getLogger(__name__)


class LiquipediaAccessRequiredError(DataProviderError):
    """Raised until approved LiquipediaDB endpoint documentation is available."""


class LiquipediaPayloadError(DataProviderError):
    """The Liquipedia API returned a successful response with invalid JSON."""


@dataclass(slots=True)
class _CachedResponse:
    value: Any
    expires_at: float


class LiquipediaHttpClient:
    """Terms-compliant reusable transport for documented Liquipedia API requests."""

    def __init__(
        self,
        settings: LiquipediaClientSettings,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        if settings.minimum_request_interval_seconds < 2:
            raise ValueError("Liquipedia requests must be at least two seconds apart")
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "User-Agent": settings.user_agent,
            },
        )
        if client is not None:
            self._client.headers.update(
                {
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "User-Agent": settings.user_agent,
                }
            )
        self._cache: dict[str, _CachedResponse] = {}
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_at: float | None = None

    async def get_json(self, url: str, params: Mapping[str, str] | None = None) -> Any:
        """Fetch a caller-supplied, documented endpoint with cache and rate limiting."""

        cache_key = str(httpx.URL(url, params=params))
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached is not None and cached.expires_at > now:
            LOGGER.debug("Liquipedia cached response used")
            return cached.value

        async with self._rate_limit_lock:
            await self._wait_for_request_slot()
            LOGGER.info("Liquipedia request started")
            try:
                response = await self._client.get(url, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise DataProviderTemporaryError("Liquipedia is temporarily unavailable") from exc
            self._last_request_at = time.monotonic()

        if response.status_code == 429:
            raise DataProviderRateLimitError("Liquipedia rate limit reached")
        if response.status_code >= 500:
            raise DataProviderTemporaryError("Liquipedia is temporarily unavailable")
        if response.status_code >= 400:
            raise DataProviderError(f"Liquipedia request failed: {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise LiquipediaPayloadError("Liquipedia returned invalid JSON") from exc

        self._cache[cache_key] = _CachedResponse(
            value=payload,
            expires_at=time.monotonic() + self._settings.cache_ttl_seconds,
        )
        return payload

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _wait_for_request_slot(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self._settings.minimum_request_interval_seconds - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
