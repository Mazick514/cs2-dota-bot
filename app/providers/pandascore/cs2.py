from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from app.domain.enums import Game, MatchStatus
from app.domain.models import EsportsMatch, EsportsTeam, MatchScoreboard, PlayerMatchStats, SeriesGame, StatisticValue
from app.providers.base import CS2DataProvider, DataProviderError, DataProviderRateLimitError

LOGGER = logging.getLogger(__name__)


class PandaScorePayloadError(DataProviderError):
    """The API returned a successful response with an unexpected documented shape."""


class PandaScoreGameProvider:
    """Shared async adapter for PandaScore game-specific team and match endpoints."""

    _BASE_URL = "https://api.pandascore.co"
    _game_path: str
    game: Game

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._BASE_URL,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "esports-teams-bot/1.0"},
        )

    async def search_teams(self, query: str) -> list[EsportsTeam]:
        normalized = " ".join(query.split())
        if not normalized:
            return []

        # `name` is documented as searchable. PandaScore team records also expose
        # `acronym`, which allows natural queries such as NAVI or Spirit without fuzzy matching.
        responses = await asyncio.gather(
            self._get(f"/{self._game_path}/teams", {"search[name]": normalized, "per_page": 10}),
            self._get(f"/{self._game_path}/teams", {"search[acronym]": normalized, "per_page": 10}),
        )
        teams: dict[str, EsportsTeam] = {}
        for response in responses:
            for item in self._as_list(response, "team search"):
                team = self.parse_team(item)
                teams[team.provider_id] = team
        return sorted(teams.values(), key=lambda team: self._search_sort_key(team, normalized))

    async def get_team(self, provider_team_id: str) -> EsportsTeam:
        payload = await self._get(
            f"/{self._game_path}/teams",
            {"filter[id]": provider_team_id, "per_page": 1},
        )
        teams = self._as_list(payload, "team")
        if not teams:
            raise DataProviderError(f"{self.game.value} team was not found by PandaScore")
        return self.parse_team(teams[0])

    async def get_recent_finished_matches(self, limit: int = 100) -> list[EsportsMatch]:
        payload = await self._get(
            f"/{self._game_path}/matches/past",
            {"per_page": min(max(limit, 1), 100), "sort": "-end_at"},
        )
        return [self.parse_match(item) for item in self._as_list(payload, "past matches")]

    async def get_match_scoreboard(self, match: EsportsMatch) -> MatchScoreboard | None:
        """Fetch documented detailed endpoints without making notifications depend on them."""

        try:
            player_payload, games_payload = await asyncio.gather(
                self._get(f"/{self._game_path}/matches/{match.provider_id}/players/stats"),
                self._get(f"/{self._game_path}/matches/{match.provider_id}/games", {"per_page": 100}),
            )
            return self.parse_scoreboard(match, player_payload, games_payload)
        except DataProviderError as exc:
            LOGGER.info(
                "Detailed PandaScore statistics are unavailable; sending result without a scoreboard",
                extra={"game": self.game.value, "provider_match_id": match.provider_id, "reason": str(exc)},
            )
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.warning(
                "Detailed PandaScore statistics could not be normalized; sending result without a scoreboard",
                exc_info=exc,
                extra={"game": self.game.value, "provider_match_id": match.provider_id},
            )
        return None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        request_params = {"token": self._api_key, **(params or {})}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._client.get(path, params=request_params)
                if response.status_code == 429:
                    LOGGER.warning("PandaScore rate limit encountered")
                    raise DataProviderRateLimitError("PandaScore rate limit reached")
                if response.status_code in {401, 403}:
                    raise DataProviderError("PandaScore rejected the configured API key or plan")
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError("PandaScore server error", request=response.request, response=response)
                if response.status_code >= 400:
                    raise DataProviderError(f"PandaScore request failed: {response.status_code}")
                response.raise_for_status()
                return response.json()
            except DataProviderRateLimitError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                await asyncio.sleep(2**attempt)
            except httpx.HTTPError as exc:
                raise DataProviderError("PandaScore request failed") from exc
            except ValueError as exc:
                raise PandaScorePayloadError("PandaScore returned invalid JSON") from exc
        raise DataProviderError("PandaScore is temporarily unavailable") from last_error

    @classmethod
    def parse_team(cls, payload: Mapping[str, Any]) -> EsportsTeam:
        try:
            provider_id = str(payload["id"])
            name = cls._required_string(payload, "name")
        except (KeyError, TypeError, ValueError) as exc:
            raise PandaScorePayloadError("Team payload does not contain id and name") from exc
        return EsportsTeam(
            provider_id=provider_id,
            game=cls.game,
            name=name,
            slug=cls._optional_string(payload.get("slug")),
            acronym=cls._optional_string(payload.get("acronym")),
            # PandaScore team payload has a human-readable `location`, not an
            # ISO country code, so this remains absent rather than guessed.
            country_code=None,
            logo_url=cls._optional_string(payload.get("image_url")),
        )

    @classmethod
    def parse_match(cls, payload: Mapping[str, Any]) -> EsportsMatch:
        try:
            opponents_payload = cls._as_list(payload.get("opponents"), "opponents")
            teams = tuple(
                cls.parse_team(cls._as_mapping(item.get("opponent"), "opponent"))
                for item in opponents_payload
                if isinstance(item, Mapping) and item.get("type") == "Team"
            )
            if len(teams) != 2:
                raise PandaScorePayloadError("Finished match must have exactly two team opponents")
            first_team, second_team = teams
            result_scores = cls._scores_by_team(payload.get("results"))
            tournament = cls._as_mapping(payload.get("tournament"), "tournament")
            winner = cls._as_mapping_or_empty(payload.get("winner"))
            raw_data = dict(payload)
            return EsportsMatch(
                provider_id=str(payload["id"]),
                game=cls.game,
                status=cls._match_status(payload.get("status")),
                opponents=(first_team, second_team),
                scores=(
                    result_scores.get(first_team.provider_id),
                    result_scores.get(second_team.provider_id),
                ),
                winner_provider_team_id=cls._optional_string(winner.get("id")),
                tournament_id=cls._optional_string(tournament.get("id")),
                tournament_name=cls._optional_string(tournament.get("name")),
                started_at=cls._parse_datetime(payload.get("begin_at")),
                finished_at=cls._parse_datetime(payload.get("end_at")),
                raw_data=raw_data,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PandaScorePayloadError("Match payload cannot be parsed") from exc

    @classmethod
    def parse_scoreboard(cls, match: EsportsMatch, player_payload: Any, games_payload: Any) -> MatchScoreboard:
        """Normalize the documented detailed-match response shapes for the renderer."""

        teams_payload = cls._as_list(cls._as_mapping(player_payload, "player stats").get("teams"), "stats teams")
        games_payload_list = cls._as_list(games_payload, "match games")
        games = cls._parse_series_games(match, games_payload_list)
        hero_names_by_player = cls._hero_names_by_player(games_payload_list)
        players = cls._parse_player_statistics(teams_payload, hero_names_by_player)
        if not games or not players:
            raise PandaScorePayloadError("Detailed scoreboard has no games or player statistics")
        return MatchScoreboard(match=match, games=games, players=players)

    @classmethod
    def _parse_series_games(cls, match: EsportsMatch, games_payload: list[Mapping[str, Any]]) -> tuple[SeriesGame, ...]:
        parsed: list[SeriesGame] = []
        first_team_id, second_team_id = (team.provider_id for team in match.opponents)
        for fallback_position, game in enumerate(games_payload, start=1):
            position = cls._positive_int_or_default(game.get("position"), fallback_position)
            winner = cls._optional_provider_id(cls._as_mapping_or_empty(game.get("winner")).get("id"))
            if cls.game is Game.CS2:
                map_payload = cls._as_mapping_or_empty(game.get("map"))
                map_name = cls._optional_string(map_payload.get("name"))
                scores = cls._cs2_game_scores(game, first_team_id, second_team_id)
                label = map_name or f"Map {position}"
            else:
                scores = cls._dota2_game_scores(game, first_team_id, second_team_id)
                label = f"Game {position}"
            parsed.append(
                SeriesGame(
                    position=position,
                    label=label,
                    scores=scores,
                    winner_provider_team_id=winner,
                )
            )
        return tuple(sorted(parsed, key=lambda game: game.position))

    @classmethod
    def _cs2_game_scores(
        cls, game: Mapping[str, Any], first_team_id: str, second_team_id: str
    ) -> tuple[int | None, int | None]:
        rounds = cls._as_list(game.get("rounds"), "CS2 game rounds")
        first_score = sum(
            1
            for round_payload in rounds
            if cls._optional_provider_id(round_payload.get("winner_team")) == first_team_id
        )
        second_score = sum(
            1
            for round_payload in rounds
            if cls._optional_provider_id(round_payload.get("winner_team")) == second_team_id
        )
        if first_score == 0 and second_score == 0:
            raise PandaScorePayloadError("CS2 game does not contain round winners")
        return (first_score, second_score)

    @classmethod
    def _dota2_game_scores(
        cls, game: Mapping[str, Any], first_team_id: str, second_team_id: str
    ) -> tuple[int | None, int | None]:
        scores: dict[str, int] = {}
        for team_payload in cls._as_list(game.get("teams"), "Dota 2 game teams"):
            team = cls._as_mapping(team_payload.get("team"), "Dota 2 game team")
            team_id = cls._optional_provider_id(team.get("id"))
            score = cls._integer(team_payload.get("score"))
            if team_id is not None and score is not None:
                scores[team_id] = score
        if first_team_id not in scores or second_team_id not in scores:
            raise PandaScorePayloadError("Dota 2 game does not contain both team scores")
        return (scores[first_team_id], scores[second_team_id])

    @classmethod
    def _parse_player_statistics(
        cls, teams_payload: list[Mapping[str, Any]], hero_names_by_player: dict[str, tuple[str, ...]]
    ) -> tuple[PlayerMatchStats, ...]:
        players: list[PlayerMatchStats] = []
        for team_payload in teams_payload:
            team_id = cls._optional_provider_id(team_payload.get("id"))
            if team_id is None:
                raise PandaScorePayloadError("Statistics team lacks id")
            for player_payload in cls._as_list(team_payload.get("players"), "team players"):
                player_id = cls._optional_provider_id(player_payload.get("id"))
                player_name = cls._optional_string(player_payload.get("name"))
                stats = cls._as_mapping(player_payload.get("stats"), "player stats")
                if player_id is None or player_name is None:
                    raise PandaScorePayloadError("Statistics player lacks id or name")
                statistics = (
                    cls._cs2_player_statistics(stats) if cls.game is Game.CS2 else cls._dota2_player_statistics(stats)
                )
                players.append(
                    PlayerMatchStats(
                        provider_player_id=player_id,
                        player_name=player_name,
                        team_provider_id=team_id,
                        hero_names=hero_names_by_player.get(player_id, ()),
                        statistics=statistics,
                    )
                )
        return tuple(players)

    @classmethod
    def _cs2_player_statistics(cls, stats: Mapping[str, Any]) -> tuple[tuple[str, StatisticValue], ...]:
        counts = cls._as_mapping(stats.get("counts"), "CS2 player counts")
        averages = cls._as_mapping(stats.get("per_game_averages"), "CS2 player per-game averages")
        return cls._statistics(
            (
                ("kills", counts.get("kills")),
                ("assists", counts.get("assists")),
                ("deaths", counts.get("deaths")),
                ("k_d_diff", counts.get("k_d_diff")),
                ("kast", averages.get("kast")),
                ("adr", averages.get("adr")),
                ("rating", averages.get("hltv_game_rating")),
                ("headshots", counts.get("headshots")),
                ("first_kills_diff", counts.get("first_kills_diff")),
                ("flash_assists", counts.get("flash_assists")),
                ("clutch_rounds_won", counts.get("clutch_rounds_won")),
                ("multi_kills", counts.get("multi_kills")),
                ("utility_kills", counts.get("utility_kills")),
            )
        )

    @classmethod
    def _dota2_player_statistics(cls, stats: Mapping[str, Any]) -> tuple[tuple[str, StatisticValue], ...]:
        totals = cls._as_mapping(stats.get("totals"), "Dota 2 player totals")
        averages = cls._as_mapping(stats.get("averages"), "Dota 2 player averages")
        return cls._statistics(
            (
                ("kills", totals.get("kills")),
                ("deaths", totals.get("deaths")),
                ("assists", totals.get("assists")),
                ("gpm", averages.get("gold_per_minute")),
                ("xpm", averages.get("xp_per_minute")),
                ("last_hits", averages.get("last_hits")),
                ("denies", averages.get("denies")),
                ("hero_damage", averages.get("hero_damage")),
                ("tower_damage", averages.get("tower_damage")),
                ("kill_participation", averages.get("kill_participation")),
                ("wards_placed", averages.get("wards_placed")),
            )
        )

    @classmethod
    def _hero_names_by_player(cls, games_payload: list[Mapping[str, Any]]) -> dict[str, tuple[str, ...]]:
        if cls.game is not Game.DOTA2:
            return {}
        heroes: dict[str, list[str]] = {}
        for game_payload in games_payload:
            for player_payload in cls._as_list(game_payload.get("players"), "Dota 2 game players"):
                player = cls._as_mapping(player_payload.get("player"), "Dota 2 game player")
                hero = cls._as_mapping_or_empty(player_payload.get("hero"))
                player_id = cls._optional_provider_id(player.get("id"))
                hero_name = cls._optional_string(hero.get("localized_name")) or cls._optional_string(hero.get("name"))
                if player_id is not None and hero_name is not None:
                    heroes.setdefault(player_id, []).append(hero_name)
        return {player_id: tuple(names) for player_id, names in heroes.items()}

    @staticmethod
    def _scores_by_team(value: Any) -> dict[str, int | None]:
        results: dict[str, int | None] = {}
        for item in PandaScoreGameProvider._as_list(value, "results"):
            if not isinstance(item, Mapping) or "team_id" not in item:
                raise PandaScorePayloadError("Result payload lacks team_id")
            score = item.get("score")
            if score is not None and not isinstance(score, int):
                raise PandaScorePayloadError("Result score is not an integer")
            results[str(item["team_id"])] = score
        return results

    @staticmethod
    def _match_status(value: Any) -> MatchStatus:
        try:
            return MatchStatus(str(value))
        except ValueError:
            return MatchStatus.UNKNOWN

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise PandaScorePayloadError("Date is not an ISO-8601 string")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed

    @staticmethod
    def _required_string(payload: Mapping[str, Any], key: str) -> str:
        value = payload[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} is not a non-empty string")
        return value

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (str, int)):
            return str(value) or None
        raise PandaScorePayloadError("Expected an optional string")

    @staticmethod
    def _optional_provider_id(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return str(value)
        raise PandaScorePayloadError("Expected an optional provider id")

    @staticmethod
    def _integer(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise PandaScorePayloadError("Expected an integer")

    @staticmethod
    def _positive_int_or_default(value: Any, default: int) -> int:
        parsed = PandaScoreGameProvider._integer(value)
        return parsed if parsed is not None and parsed > 0 else default

    @staticmethod
    def _statistics(values: tuple[tuple[str, Any], ...]) -> tuple[tuple[str, StatisticValue], ...]:
        parsed: list[tuple[str, StatisticValue]] = []
        for key, value in values:
            if value is None:
                continue
            if isinstance(value, (int, float, str)) and not isinstance(value, bool):
                parsed.append((key, value))
            else:
                raise PandaScorePayloadError(f"Statistic {key} is not a scalar value")
        return tuple(parsed)

    @staticmethod
    def _as_list(value: Any, label: str) -> list[Mapping[str, Any]]:
        if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
            raise PandaScorePayloadError(f"{label} response is not a list of objects")
        return list(value)

    @staticmethod
    def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise PandaScorePayloadError(f"{label} response is not an object")
        return value

    @staticmethod
    def _as_mapping_or_empty(value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _search_sort_key(team: EsportsTeam, query: str) -> tuple[int, str]:
        needle = " ".join(query.casefold().split())
        fields = (team.name, team.acronym or "", team.slug or "")
        exact = any(" ".join(field.casefold().split()) == needle for field in fields)
        return (0 if exact else 1, team.name.casefold())


class PandaScoreCS2Provider(PandaScoreGameProvider, CS2DataProvider):
    """Async adapter for PandaScore's documented `/csgo/` CS2 REST API."""

    _game_path = "csgo"
