from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.enums import Game, MatchStatus


@dataclass(frozen=True, slots=True)
class EsportsTeam:
    provider_id: str
    game: Game
    name: str
    slug: str | None = None
    acronym: str | None = None
    country_code: str | None = None
    logo_url: str | None = None


@dataclass(frozen=True, slots=True)
class EsportsMatch:
    provider_id: str
    game: Game
    status: MatchStatus
    opponents: tuple[EsportsTeam, EsportsTeam]
    scores: tuple[int | None, int | None]
    winner_provider_team_id: str | None
    tournament_id: str | None
    tournament_name: str | None
    started_at: datetime | None
    finished_at: datetime | None
    raw_data: dict[str, Any]

    def includes_team(self, provider_team_id: str) -> bool:
        return any(team.provider_id == provider_team_id for team in self.opponents)


type StatisticValue = int | float | str


@dataclass(frozen=True, slots=True)
class SeriesGame:
    """A single completed map (CS2) or game (Dota 2), in match team order."""

    position: int
    label: str
    scores: tuple[int | None, int | None]
    winner_provider_team_id: str | None


@dataclass(frozen=True, slots=True)
class PlayerMatchStats:
    """Provider-neutral player row for a finished-match scoreboard."""

    provider_player_id: str
    player_name: str
    team_provider_id: str
    hero_names: tuple[str, ...]
    statistics: tuple[tuple[str, StatisticValue], ...]

    def value(self, key: str) -> StatisticValue | None:
        for statistic_key, statistic_value in self.statistics:
            if statistic_key == key:
                return statistic_value
        return None


@dataclass(frozen=True, slots=True)
class MatchScoreboard:
    """Normalized detailed result. Renderers consume this instead of provider payloads."""

    match: EsportsMatch
    games: tuple[SeriesGame, ...]
    players: tuple[PlayerMatchStats, ...]
