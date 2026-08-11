from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiquipediaClientSettings:
    """Transport settings required by Liquipedia's MediaWiki API terms."""

    user_agent: str
    cache_ttl_seconds: int
    minimum_request_interval_seconds: float
