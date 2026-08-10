from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.enums import Game
from app.domain.models import EsportsMatch, EsportsTeam, MatchScoreboard


class DataProviderError(Exception):
    """A non-retriable or already-exhausted external data provider error."""


class DataProviderTemporaryError(DataProviderError):
    """An unavailable provider which may succeed on a later polling cycle."""


class DataProviderRateLimitError(DataProviderTemporaryError):
    """The provider has explicitly rate limited this client."""


class EsportsDataProvider(ABC):
    """Game-agnostic contract used by services and workers, never Telegram handlers."""

    game: Game

    @abstractmethod
    async def search_teams(self, query: str) -> list[EsportsTeam]:
        raise NotImplementedError

    @abstractmethod
    async def get_team(self, provider_team_id: str) -> EsportsTeam:
        raise NotImplementedError

    @abstractmethod
    async def get_recent_finished_matches(self, limit: int = 100) -> list[EsportsMatch]:
        raise NotImplementedError

    async def get_match_scoreboard(self, match: EsportsMatch) -> MatchScoreboard | None:
        """Return normalized detailed result when the provider plan/data permits it.

        Detailed statistics are intentionally optional: a match result notification must
        still be delivered when an API plan does not expose them.
        """

        return None

    @abstractmethod
    async def aclose(self) -> None:
        raise NotImplementedError


class CS2DataProvider(EsportsDataProvider, ABC):
    """CS2-specific provider contract."""

    game = Game.CS2


class Dota2DataProvider(EsportsDataProvider, ABC):
    """Dota 2-specific provider contract."""

    game = Game.DOTA2
