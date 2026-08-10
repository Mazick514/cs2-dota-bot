from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.database.models import Team
from app.database.repositories.teams import TeamRepository
from app.domain.enums import Game
from app.domain.models import EsportsTeam
from app.providers.base import EsportsDataProvider


class TrackingResult(StrEnum):
    ADDED = "added"
    ALREADY_TRACKED = "already_tracked"


@dataclass(frozen=True, slots=True)
class TrackingOutcome:
    team: Team
    result: TrackingResult


class TeamService:
    """Business rules for chat-scoped tracking; no Telegram or SQL in handlers."""

    def __init__(self, repository: TeamRepository, provider: EsportsDataProvider, game: Game) -> None:
        self._repository = repository
        self._provider = provider
        self._game = game

    async def search(self, query: str) -> list[EsportsTeam]:
        return await self._provider.search_teams(query)

    async def add_by_provider_id(self, chat_id: int, provider_team_id: str) -> TrackingOutcome:
        team_data = await self._provider.get_team(provider_team_id)
        if team_data.game is not self._game:
            raise ValueError("Provider returned a team for another game")
        team = await self._repository.get_or_create(team_data)
        added = await self._repository.add_tracking(chat_id, team, self._game)
        return TrackingOutcome(team=team, result=TrackingResult.ADDED if added else TrackingResult.ALREADY_TRACKED)

    async def list_for_chat(self, chat_id: int) -> list[Team]:
        return await self._repository.list_tracked(chat_id, self._game)

    async def remove_by_local_id(self, chat_id: int, team_id: int) -> Team | None:
        return await self._repository.remove_tracking(chat_id, team_id, self._game)

    async def remove_by_query(self, chat_id: int, query: str) -> list[Team]:
        """Find exact known names/acronyms/slugs only; never silently fuzzy-remove."""
        return await self._repository.find_tracked_exact(chat_id, self._game, query)
