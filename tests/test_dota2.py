from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.database.database import Database
from app.database.repositories.groups import GroupRepository
from app.database.repositories.teams import TeamRepository
from app.domain.enums import Game, MatchStatus
from app.domain.models import EsportsMatch, EsportsTeam
from app.providers.pandascore import PandaScoreDota2Provider
from app.services.teams import TeamService
from tests.conftest import FakeCS2Provider, FakeDota2Provider


async def test_dota_tracking_is_independent_from_cs2_in_same_group(
    database: Database,
    navi: EsportsTeam,
    spirit: EsportsTeam,
) -> None:
    await GroupRepository(database).upsert(100, "supergroup", "One", is_active=True)
    repository = TeamRepository(database)
    cs2_service = TeamService(repository, FakeCS2Provider(teams={"1": navi}), Game.CS2)
    dota_service = TeamService(repository, FakeDota2Provider(teams={"1": spirit}), Game.DOTA2)

    await cs2_service.add_by_provider_id(100, "1")
    await dota_service.add_by_provider_id(100, "1")

    assert [team.name for team in await cs2_service.list_for_chat(100)] == ["Natus Vincere"]
    assert [team.name for team in await dota_service.list_for_chat(100)] == ["Team Spirit"]


async def test_dota_provider_uses_documented_team_and_past_match_endpoints() -> None:
    paths: list[str] = []

    def response_handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.url.params["token"] == "token"
        if request.url.path == "/dota2/teams":
            return httpx.Response(
                200,
                json=[{"id": 1, "name": "Team Spirit", "acronym": "Spirit", "slug": "team-spirit"}],
            )
        if request.url.path == "/dota2/matches/past":
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={})

    client = httpx.AsyncClient(
        base_url="https://api.pandascore.co",
        transport=httpx.MockTransport(response_handler),
    )
    provider = PandaScoreDota2Provider("token", client=client)

    found = await provider.search_teams("Spirit")
    matches = await provider.get_recent_finished_matches()

    assert found[0].game is Game.DOTA2
    assert matches == []
    assert paths.count("/dota2/teams") == 2
    assert "/dota2/matches/past" in paths
    await client.aclose()


def test_dota_match_parser_marks_dota2_game(spirit: EsportsTeam, liquid: EsportsTeam) -> None:
    payload = {
        "id": 501,
        "status": "finished",
        "begin_at": "2099-08-01T10:00:00Z",
        "end_at": "2099-08-01T12:00:00Z",
        "opponents": [
            {"type": "Team", "opponent": {"id": 1, "name": spirit.name, "acronym": "Spirit"}},
            {"type": "Team", "opponent": {"id": 2, "name": liquid.name, "acronym": "Liquid"}},
        ],
        "results": [{"team_id": 1, "score": 2}, {"team_id": 2, "score": 1}],
        "winner": {"id": 1, "type": "Team"},
        "tournament": {"id": 90, "name": "The International 2026"},
    }

    match = PandaScoreDota2Provider.parse_match(payload)

    assert match.game is Game.DOTA2
    assert match.status is MatchStatus.FINISHED
    assert match.tournament_name == "The International 2026"
    assert match.finished_at == datetime(2099, 8, 1, 12, tzinfo=UTC)


def test_dota_finished_match_fixture(spirit: EsportsTeam, liquid: EsportsTeam) -> None:
    match = EsportsMatch(
        provider_id="dota-match-1",
        game=Game.DOTA2,
        status=MatchStatus.FINISHED,
        opponents=(spirit, liquid),
        scores=(2, 1),
        winner_provider_team_id=spirit.provider_id,
        tournament_id="ti-2026",
        tournament_name="The International 2026",
        started_at=datetime(2099, 8, 1, 10, tzinfo=UTC),
        finished_at=datetime(2099, 8, 1, 12, tzinfo=UTC),
        raw_data={"id": "dota-match-1"},
    )
    assert match.includes_team(spirit.provider_id)
