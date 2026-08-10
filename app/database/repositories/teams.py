from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import Database
from app.database.models import Group, Team, TrackedTeam
from app.domain.enums import Game
from app.domain.models import EsportsTeam


@dataclass(frozen=True, slots=True)
class TeamSubscription:
    chat_id: int
    team: Team
    tracked_at: datetime


class TeamRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_or_create(self, esports_team: EsportsTeam) -> Team:
        async with self._database.session() as session:
            team = await self._get_by_provider_id(session, esports_team.provider_id, esports_team.game)
            if team is None:
                team = Team(
                    provider_team_id=esports_team.provider_id,
                    game=esports_team.game.value,
                    name=esports_team.name,
                )
                session.add(team)
            team.name = esports_team.name
            team.slug = esports_team.slug
            team.acronym = esports_team.acronym
            team.country_code = esports_team.country_code
            team.logo_url = esports_team.logo_url
            await session.commit()
            return team

    async def add_tracking(self, chat_id: int, team: Team, game: Game) -> bool:
        async with self._database.session() as session:
            query = select(TrackedTeam.id).where(
                TrackedTeam.chat_id == chat_id,
                TrackedTeam.team_id == team.id,
                TrackedTeam.game == game.value,
            )
            if (await session.scalar(query)) is not None:
                return False
            session.add(TrackedTeam(chat_id=chat_id, team_id=team.id, game=game.value))
            await session.commit()
            return True

    async def list_tracked(self, chat_id: int, game: Game) -> list[Team]:
        async with self._database.session() as session:
            statement = (
                select(Team)
                .join(TrackedTeam, TrackedTeam.team_id == Team.id)
                .where(TrackedTeam.chat_id == chat_id, TrackedTeam.game == game.value)
                .order_by(Team.name)
            )
            return list((await session.scalars(statement)).all())

    async def find_tracked_exact(self, chat_id: int, game: Game, query: str) -> list[Team]:
        normalized = self._normalize(query)
        if not normalized:
            return []
        async with self._database.session() as session:
            statement = (
                select(Team)
                .join(TrackedTeam, TrackedTeam.team_id == Team.id)
                .where(TrackedTeam.chat_id == chat_id, TrackedTeam.game == game.value)
            )
            candidates = list((await session.scalars(statement)).all())
        return [
            team
            for team in candidates
            if normalized
            in {
                self._normalize(team.name),
                self._normalize(team.acronym or ""),
                self._normalize(team.slug or ""),
            }
        ]

    async def remove_tracking(self, chat_id: int, team_id: int, game: Game) -> Team | None:
        async with self._database.session() as session:
            statement = (
                select(TrackedTeam, Team)
                .join(Team, Team.id == TrackedTeam.team_id)
                .where(
                    TrackedTeam.chat_id == chat_id,
                    TrackedTeam.team_id == team_id,
                    TrackedTeam.game == game.value,
                )
            )
            pair = cast(
                tuple[TrackedTeam, Team] | None,
                (await session.execute(statement)).one_or_none(),
            )
            if pair is None:
                return None
            tracked, team = pair
            await session.delete(tracked)
            await session.commit()
            return team

    async def list_active_subscriptions(self, game: Game) -> list[TeamSubscription]:
        async with self._database.session() as session:
            statement = (
                select(Group.chat_id, Team, TrackedTeam.created_at)
                .join(TrackedTeam, TrackedTeam.chat_id == Group.chat_id)
                .join(Team, Team.id == TrackedTeam.team_id)
                .where(Group.is_active.is_(True), TrackedTeam.game == game.value)
            )
            rows = (await session.execute(statement)).all()
            return [
                TeamSubscription(
                    chat_id=chat_id,
                    team=team,
                    tracked_at=tracked_at.replace(tzinfo=UTC) if tracked_at.tzinfo is None else tracked_at,
                )
                for chat_id, team, tracked_at in rows
            ]

    @staticmethod
    async def _get_by_provider_id(session: AsyncSession, provider_id: str, game: Game) -> Team | None:
        statement = select(Team).where(
            Team.provider_team_id == provider_id,
            Team.game == game.value,
        )
        return cast(Team | None, await session.scalar(statement))

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())
