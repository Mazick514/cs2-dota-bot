from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.database.repositories.teams import TeamRepository
from app.domain.enums import Game, MatchStatus
from app.domain.models import EsportsMatch, EsportsTeam
from app.providers.base import CS2DataProvider
from app.workers.match_tracker import MatchTracker

_TEST_TEAM_ALPHA = EsportsTeam(
    provider_id="test-mode-team-alpha",
    game=Game.CS2,
    name="Test Team Alpha",
    acronym="ALPHA",
)
_TEST_TEAM_BETA = EsportsTeam(
    provider_id="test-mode-team-beta",
    game=Game.CS2,
    name="Test Team Beta",
    acronym="BETA",
)


class _TestMatchProvider(CS2DataProvider):
    def __init__(self, match: EsportsMatch) -> None:
        self._match = match

    async def search_teams(self, query: str) -> list[EsportsTeam]:
        return []

    async def get_team(self, provider_team_id: str) -> EsportsTeam:
        raise LookupError("Test match provider does not expose teams")

    async def get_recent_finished_matches(self, limit: int = 100) -> list[EsportsMatch]:
        return [self._match][:limit]

    async def aclose(self) -> None:
        return None


@dataclass(frozen=True, slots=True)
class ApiCheckResult:
    match_count: int


class TestModeService:
    """Runs administrator-requested diagnostics through production dependencies."""

    def __init__(self, *, cs2_provider: CS2DataProvider, teams: TeamRepository, tracker: MatchTracker) -> None:
        self._cs2_provider = cs2_provider
        self._teams = teams
        self._tracker = tracker

    async def check_api(self) -> ApiCheckResult:
        matches = await self._cs2_provider.get_recent_finished_matches()
        return ApiCheckResult(match_count=len(matches))

    async def process_test_match(self, chat_id: int) -> int:
        test_team = await self._teams.get_or_create(_TEST_TEAM_ALPHA)
        added = await self._teams.add_tracking(chat_id, test_team, Game.CS2)
        try:
            return await self._tracker.process_provider(_TestMatchProvider(self._test_match()))
        finally:
            if added:
                await self._teams.remove_tracking(chat_id, test_team.id, Game.CS2)

    @staticmethod
    def _test_match() -> EsportsMatch:
        finished_at = datetime.now(UTC)
        return EsportsMatch(
            provider_id="test-mode-cs2-match-v1",
            game=Game.CS2,
            status=MatchStatus.FINISHED,
            opponents=(_TEST_TEAM_ALPHA, _TEST_TEAM_BETA),
            scores=(2, 1),
            winner_provider_team_id=_TEST_TEAM_ALPHA.provider_id,
            tournament_id="test-mode-tournament",
            tournament_name="Test Tournament",
            started_at=finished_at - timedelta(minutes=45),
            finished_at=finished_at,
            raw_data={"source": "test_mode"},
        )
