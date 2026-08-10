from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.database.database import Database
from app.database.repositories.groups import GroupRepository
from app.database.repositories.matches import MatchRepository
from app.database.repositories.notifications import NotificationRepository
from app.database.repositories.teams import TeamRepository
from app.domain.enums import Game, MatchStatus, NotificationType
from app.domain.models import EsportsMatch, EsportsTeam
from app.services.matches import MatchService
from app.services.notifications import NotificationService
from app.services.teams import TeamService
from app.workers.match_tracker import MatchTracker
from tests.conftest import FakeCS2Provider


@dataclass
class FakeSender:
    messages: list[tuple[int, str]] = field(default_factory=list)

    async def send_message(self, chat_id: int, text: str) -> object:
        self.messages.append((chat_id, text))
        return object()


def _finished_match(navi: EsportsTeam, g2: EsportsTeam) -> EsportsMatch:
    return EsportsMatch(
        provider_id="match-1",
        game=Game.CS2,
        status=MatchStatus.FINISHED,
        opponents=(navi, g2),
        scores=(2, 1),
        winner_provider_team_id=navi.provider_id,
        tournament_id="tournament-1",
        tournament_name="IEM Cologne 2026",
        started_at=datetime(2099, 8, 1, 10, tzinfo=UTC),
        finished_at=datetime(2099, 8, 1, 12, tzinfo=UTC),
        raw_data={"id": "match-1"},
    )


async def test_notification_deduplication(database: Database, navi: EsportsTeam, g2: EsportsTeam) -> None:
    groups = GroupRepository(database)
    await groups.upsert(100, "supergroup", "One", is_active=True)
    teams = TeamRepository(database)
    match_service = MatchService(teams, MatchRepository(database))
    stored = await match_service.store_finished_match(_finished_match(navi, g2))
    notifications = NotificationRepository(database)

    assert await notifications.reserve(100, stored.id, NotificationType.MATCH_FINISHED)
    assert not await notifications.reserve(100, stored.id, NotificationType.MATCH_FINISHED)


async def test_finished_match_is_sent_once_after_restart_safe_polling(
    database: Database, navi: EsportsTeam, g2: EsportsTeam
) -> None:
    groups = GroupRepository(database)
    await groups.upsert(100, "supergroup", "One", is_active=True)
    provider = FakeCS2Provider(
        teams={navi.provider_id: navi, g2.provider_id: g2},
        finished_matches=[_finished_match(navi, g2)],
    )
    teams = TeamRepository(database)
    team_service = TeamService(teams, provider, Game.CS2)
    await team_service.add_by_provider_id(100, navi.provider_id)
    sender = FakeSender()
    tracker = MatchTracker(
        providers=(provider,),
        teams=teams,
        matches=MatchService(teams, MatchRepository(database)),
        notifications=NotificationService(NotificationRepository(database), sender),
        interval_seconds=60,
    )

    await tracker.run_once()
    await tracker.run_once()

    assert len(sender.messages) == 1
    assert sender.messages[0][0] == 100
    assert "Natus Vincere ПОБЕДИЛИ" in sender.messages[0][1]
