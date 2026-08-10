from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
import pytest_asyncio

from app.database.database import Database
from app.domain.enums import Game
from app.domain.models import EsportsMatch, EsportsTeam
from app.providers.base import CS2DataProvider, DataProviderError, Dota2DataProvider


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> Database:
    database_path = tmp_path / "bot.db"
    db = Database(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    await db.create_schema()
    yield db
    await db.dispose()


@dataclass
class FakeCS2Provider(CS2DataProvider):
    teams: dict[str, EsportsTeam] = field(default_factory=dict)
    search_results: list[EsportsTeam] = field(default_factory=list)
    finished_matches: list[EsportsMatch] = field(default_factory=list)
    fail: bool = False

    async def search_teams(self, query: str) -> list[EsportsTeam]:
        if self.fail:
            raise DataProviderError("offline")
        return list(self.search_results)

    async def get_team(self, provider_team_id: str) -> EsportsTeam:
        if self.fail:
            raise DataProviderError("offline")
        return self.teams[provider_team_id]

    async def get_recent_finished_matches(self, limit: int = 100) -> list[EsportsMatch]:
        if self.fail:
            raise DataProviderError("offline")
        return self.finished_matches[:limit]

    async def aclose(self) -> None:
        return None


@dataclass
class FakeDota2Provider(Dota2DataProvider):
    teams: dict[str, EsportsTeam] = field(default_factory=dict)
    search_results: list[EsportsTeam] = field(default_factory=list)
    finished_matches: list[EsportsMatch] = field(default_factory=list)
    fail: bool = False

    async def search_teams(self, query: str) -> list[EsportsTeam]:
        if self.fail:
            raise DataProviderError("offline")
        return list(self.search_results)

    async def get_team(self, provider_team_id: str) -> EsportsTeam:
        if self.fail:
            raise DataProviderError("offline")
        return self.teams[provider_team_id]

    async def get_recent_finished_matches(self, limit: int = 100) -> list[EsportsMatch]:
        if self.fail:
            raise DataProviderError("offline")
        return self.finished_matches[:limit]

    async def aclose(self) -> None:
        return None


@pytest.fixture
def navi() -> EsportsTeam:
    return EsportsTeam(
        provider_id="1",
        game=Game.CS2,
        name="Natus Vincere",
        acronym="NAVI",
        slug="natus-vincere",
        logo_url="https://example.test/navi.png",
    )


@pytest.fixture
def g2() -> EsportsTeam:
    return EsportsTeam(provider_id="2", game=Game.CS2, name="G2 Esports", acronym="G2", slug="g2")


@pytest.fixture
def spirit() -> EsportsTeam:
    return EsportsTeam(
        provider_id="1",
        game=Game.DOTA2,
        name="Team Spirit",
        acronym="Spirit",
        slug="team-spirit",
    )


@pytest.fixture
def liquid() -> EsportsTeam:
    return EsportsTeam(
        provider_id="2",
        game=Game.DOTA2,
        name="Team Liquid",
        acronym="Liquid",
        slug="team-liquid",
    )
