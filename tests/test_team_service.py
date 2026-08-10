from __future__ import annotations

import pytest

from app.database.database import Database
from app.database.repositories.groups import GroupRepository
from app.database.repositories.teams import TeamRepository
from app.domain.enums import Game
from app.domain.models import EsportsTeam
from app.providers.base import DataProviderError
from app.services.teams import TeamService, TrackingResult
from tests.conftest import FakeCS2Provider


async def _service(database: Database, provider: FakeCS2Provider, *chat_ids: int) -> TeamService:
    groups = GroupRepository(database)
    for chat_id in chat_ids:
        await groups.upsert(chat_id, "supergroup", f"Group {chat_id}", is_active=True)
    return TeamService(TeamRepository(database), provider, Game.CS2)


async def test_add_team(database: Database, navi: EsportsTeam) -> None:
    service = await _service(database, FakeCS2Provider(teams={navi.provider_id: navi}), 100)

    outcome = await service.add_by_provider_id(100, navi.provider_id)

    assert outcome.result is TrackingResult.ADDED
    assert [team.name for team in await service.list_for_chat(100)] == ["Natus Vincere"]


async def test_duplicate_team_is_not_added_twice(database: Database, navi: EsportsTeam) -> None:
    service = await _service(database, FakeCS2Provider(teams={navi.provider_id: navi}), 100)

    await service.add_by_provider_id(100, navi.provider_id)
    duplicate = await service.add_by_provider_id(100, navi.provider_id)

    assert duplicate.result is TrackingResult.ALREADY_TRACKED
    assert len(await service.list_for_chat(100)) == 1


async def test_remove_team_by_exact_acronym(database: Database, navi: EsportsTeam) -> None:
    service = await _service(database, FakeCS2Provider(teams={navi.provider_id: navi}), 100)
    await service.add_by_provider_id(100, navi.provider_id)

    candidates = await service.remove_by_query(100, "  navi ")
    removed = await service.remove_by_local_id(100, candidates[0].id)

    assert removed is not None
    assert removed.name == "Natus Vincere"
    assert await service.list_for_chat(100) == []


async def test_removing_absent_team_returns_no_candidates(database: Database, navi: EsportsTeam) -> None:
    service = await _service(database, FakeCS2Provider(teams={navi.provider_id: navi}), 100)

    assert await service.remove_by_query(100, "NAVI") == []


async def test_groups_have_independent_team_lists(database: Database, navi: EsportsTeam, g2: EsportsTeam) -> None:
    service = await _service(
        database,
        FakeCS2Provider(teams={navi.provider_id: navi, g2.provider_id: g2}),
        100,
        200,
    )

    await service.add_by_provider_id(100, navi.provider_id)
    await service.add_by_provider_id(200, g2.provider_id)

    assert [team.name for team in await service.list_for_chat(100)] == ["Natus Vincere"]
    assert [team.name for team in await service.list_for_chat(200)] == ["G2 Esports"]


async def test_provider_error_is_exposed_to_handler_layer(database: Database, navi: EsportsTeam) -> None:
    service = await _service(database, FakeCS2Provider(teams={navi.provider_id: navi}, fail=True), 100)

    with pytest.raises(DataProviderError):
        await service.search("NAVI")
