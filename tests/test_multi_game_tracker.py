from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.database.database import Database
from app.database.repositories.groups import GroupRepository
from app.database.repositories.matches import MatchRepository
from app.database.repositories.notifications import NotificationRepository
from app.database.repositories.teams import TeamRepository
from app.domain.enums import Game, MatchStatus
from app.domain.models import EsportsMatch, EsportsTeam
from app.services.matches import MatchService
from app.services.notifications import NotificationService
from app.services.teams import TeamService
from app.workers.match_tracker import MatchTracker
from tests.conftest import FakeCS2Provider, FakeDota2Provider


@dataclass
class FakeSender:
    messages: list[tuple[int, str]] = field(default_factory=list)

    async def send_message(self, chat_id: int, text: str) -> object:
        self.messages.append((chat_id, text))
        return object()


def _finished_match(
    provider_id: str,
    game: Game,
    first: EsportsTeam,
    second: EsportsTeam,
    tournament: str,
) -> EsportsMatch:
    return EsportsMatch(
        provider_id=provider_id,
        game=game,
        status=MatchStatus.FINISHED,
        opponents=(first, second),
        scores=(2, 1),
        winner_provider_team_id=first.provider_id,
        tournament_id=f"{provider_id}-tournament",
        tournament_name=tournament,
        started_at=datetime(2099, 8, 1, 10, tzinfo=UTC),
        finished_at=datetime(2099, 8, 1, 12, tzinfo=UTC),
        raw_data={"id": provider_id},
    )


async def test_tracker_processes_cs2_and_dota2_for_the_same_group(
    database: Database,
    navi: EsportsTeam,
    g2: EsportsTeam,
    spirit: EsportsTeam,
    liquid: EsportsTeam,
) -> None:
    await GroupRepository(database).upsert(100, "supergroup", "One", is_active=True)
    cs2_provider = FakeCS2Provider(
        teams={navi.provider_id: navi, g2.provider_id: g2},
        finished_matches=[_finished_match("cs2-match-1", Game.CS2, navi, g2, "IEM Cologne 2026")],
    )
    dota_provider = FakeDota2Provider(
        teams={spirit.provider_id: spirit, liquid.provider_id: liquid},
        finished_matches=[_finished_match("dota-match-1", Game.DOTA2, spirit, liquid, "The International 2026")],
    )
    teams = TeamRepository(database)
    await TeamService(teams, cs2_provider, Game.CS2).add_by_provider_id(100, navi.provider_id)
    await TeamService(teams, dota_provider, Game.DOTA2).add_by_provider_id(100, spirit.provider_id)
    sender = FakeSender()
    tracker = MatchTracker(
        providers=(cs2_provider, dota_provider),
        teams=teams,
        matches=MatchService(teams, MatchRepository(database)),
        notifications=NotificationService(NotificationRepository(database), sender),
        interval_seconds=60,
    )

    await tracker.run_once()

    assert len(sender.messages) == 2
    assert {chat_id for chat_id, _ in sender.messages} == {100}
    assert any("Natus Vincere" in message for _, message in sender.messages)
    assert any("Team Spirit" in message for _, message in sender.messages)
    assert any("The International 2026" in message for _, message in sender.messages)
