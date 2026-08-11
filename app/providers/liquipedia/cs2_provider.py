from __future__ import annotations

from typing import NoReturn

from app.domain.models import EsportsMatch, EsportsTeam
from app.providers.base import CS2DataProvider
from app.providers.liquipedia.base import LiquipediaAccessRequiredError, LiquipediaHttpClient


class LiquipediaCS2Provider(CS2DataProvider):
    """Inactive CS2 Liquipedia provider awaiting approved LiquipediaDB documentation."""

    def __init__(self, client: LiquipediaHttpClient) -> None:
        self._client = client

    async def search_teams(self, query: str) -> list[EsportsTeam]:
        self._require_approved_match_api()

    async def get_team(self, provider_team_id: str) -> EsportsTeam:
        self._require_approved_match_api()

    async def get_recent_finished_matches(self, limit: int = 100) -> list[EsportsMatch]:
        self._require_approved_match_api()

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _require_approved_match_api() -> NoReturn:
        # TODO(liquipedia-db): Add only approved Counter-Strike LiquipediaDB endpoints and
        # response mapping after access is granted and its dashboard documentation is available.
        raise LiquipediaAccessRequiredError("LiquipediaDB access and documented CS2 match endpoints are required")
