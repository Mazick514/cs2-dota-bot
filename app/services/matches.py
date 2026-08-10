from __future__ import annotations

from app.database.models import Match
from app.database.repositories.matches import MatchRepository
from app.database.repositories.teams import TeamRepository
from app.domain.models import EsportsMatch


class MatchService:
    def __init__(self, teams: TeamRepository, matches: MatchRepository) -> None:
        self._teams = teams
        self._matches = matches

    async def store_finished_match(self, provider_match: EsportsMatch) -> Match:
        first = await self._teams.get_or_create(provider_match.opponents[0])
        second = await self._teams.get_or_create(provider_match.opponents[1])
        return await self._matches.upsert(provider_match, first, second)
