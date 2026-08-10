from __future__ import annotations

from sqlalchemy import select

from app.database.database import Database
from app.database.models import Match, Team
from app.domain.models import EsportsMatch


class MatchRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def upsert(self, provider_match: EsportsMatch, first_team: Team, second_team: Team) -> Match:
        async with self._database.session() as session:
            statement = select(Match).where(
                Match.provider_match_id == provider_match.provider_id,
                Match.game == provider_match.game.value,
            )
            match = await session.scalar(statement)
            if match is None:
                match = Match(
                    provider_match_id=provider_match.provider_id,
                    game=provider_match.game.value,
                    tournament_id=provider_match.tournament_id,
                    tournament_name=provider_match.tournament_name,
                    team1_id=first_team.id,
                    team2_id=second_team.id,
                    status=provider_match.status.value,
                    team1_score=provider_match.scores[0],
                    team2_score=provider_match.scores[1],
                    started_at=provider_match.started_at,
                    finished_at=provider_match.finished_at,
                    raw_data=provider_match.raw_data,
                )
                session.add(match)
            else:
                match.tournament_id = provider_match.tournament_id
                match.tournament_name = provider_match.tournament_name
                match.team1_id = first_team.id
                match.team2_id = second_team.id
                match.status = provider_match.status.value
                match.team1_score = provider_match.scores[0]
                match.team2_score = provider_match.scores[1]
                match.started_at = provider_match.started_at
                match.finished_at = provider_match.finished_at
                match.raw_data = provider_match.raw_data
            await session.commit()
            return match
