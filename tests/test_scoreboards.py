from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO

import httpx
from PIL import Image

from app.database.database import Database
from app.database.repositories.groups import GroupRepository
from app.database.repositories.matches import MatchRepository
from app.database.repositories.notifications import NotificationRepository
from app.database.repositories.teams import TeamRepository
from app.domain.enums import Game, MatchStatus
from app.domain.models import EsportsMatch, EsportsTeam, MatchScoreboard, PlayerMatchStats, SeriesGame
from app.providers.pandascore import PandaScoreCS2Provider, PandaScoreDota2Provider
from app.renderers import ScoreboardRenderer
from app.services.matches import MatchService
from app.services.notifications import NotificationService


def _match(game: Game, first: EsportsTeam, second: EsportsTeam) -> EsportsMatch:
    return EsportsMatch(
        provider_id=f"{game.value}-match-1",
        game=game,
        status=MatchStatus.FINISHED,
        opponents=(first, second),
        scores=(2, 1),
        winner_provider_team_id=first.provider_id,
        tournament_id="tournament-1",
        tournament_name="The International 2026" if game is Game.DOTA2 else "IEM Cologne 2026",
        started_at=datetime(2099, 8, 1, 10, tzinfo=UTC),
        finished_at=datetime(2099, 8, 1, 12, tzinfo=UTC),
        raw_data={},
    )


def test_cs2_scoreboard_parser_uses_documented_player_and_game_fields(
    navi: EsportsTeam, g2: EsportsTeam
) -> None:
    match = _match(Game.CS2, navi, g2)
    scoreboard = PandaScoreCS2Provider.parse_scoreboard(
        match,
        {
            "teams": [
                {
                    "id": 1,
                    "players": [
                        {
                            "id": 11,
                            "name": "w0nderful",
                            "stats": {
                                "counts": {
                                    "kills": 42,
                                    "assists": 10,
                                    "deaths": 28,
                                    "headshots": 15,
                                    "first_kills_diff": 5,
                                    "flash_assists": 2,
                                    "clutch_rounds_won": 1,
                                    "multi_kills": 4,
                                    "utility_kills": 0,
                                },
                                "per_game_averages": {"kast": 76.5, "adr": 84.2, "hltv_game_rating": 1.23},
                            },
                        }
                    ],
                },
                {
                    "id": 2,
                    "players": [
                        {
                            "id": 22,
                            "name": "m0NESY",
                            "stats": {
                                "counts": {
                                    "kills": 35,
                                    "assists": 9,
                                    "deaths": 33,
                                    "headshots": 11,
                                    "first_kills_diff": 1,
                                    "flash_assists": 0,
                                    "clutch_rounds_won": 0,
                                    "multi_kills": 2,
                                    "utility_kills": 0,
                                },
                                "per_game_averages": {"kast": 69.0, "adr": 77.4, "hltv_game_rating": 1.08},
                            },
                        }
                    ],
                },
            ]
        },
        [
            {
                "position": 1,
                "map": {"name": "Mirage"},
                "winner": {"id": 1},
                "rounds": [{"winner_team": 1}] * 13 + [{"winner_team": 2}] * 8,
            }
        ],
    )

    assert scoreboard.games[0].label == "Mirage"
    assert scoreboard.games[0].scores == (13, 8)
    assert scoreboard.players[0].value("kast") == 76.5
    assert scoreboard.players[0].value("rating") == 1.23


def test_dota2_scoreboard_parser_includes_game_scores_and_heroes(
    spirit: EsportsTeam, liquid: EsportsTeam
) -> None:
    match = _match(Game.DOTA2, spirit, liquid)
    scoreboard = PandaScoreDota2Provider.parse_scoreboard(
        match,
        {
            "teams": [
                {
                    "id": 1,
                    "players": [
                        {
                            "id": 11,
                            "name": "Yatoro",
                            "stats": {
                                "totals": {"kills": 20, "deaths": 8, "assists": 19},
                                "averages": {
                                    "gold_per_minute": 702,
                                    "xp_per_minute": 744,
                                    "last_hits": 310,
                                    "denies": 11,
                                    "hero_damage": 41200,
                                    "tower_damage": 3900,
                                    "kill_participation": 68.2,
                                    "wards_placed": 0,
                                },
                            },
                        }
                    ],
                },
                {
                    "id": 2,
                    "players": [
                        {
                            "id": 22,
                            "name": "Nisha",
                            "stats": {
                                "totals": {"kills": 12, "deaths": 12, "assists": 25},
                                "averages": {
                                    "gold_per_minute": 610,
                                    "xp_per_minute": 641,
                                    "last_hits": 248,
                                    "denies": 7,
                                    "hero_damage": 36700,
                                    "tower_damage": 2100,
                                    "kill_participation": 61.5,
                                    "wards_placed": 2,
                                },
                            },
                        }
                    ],
                },
            ]
        },
        [
            {
                "position": 1,
                "winner": {"id": 1},
                "teams": [{"team": {"id": 1}, "score": 31}, {"team": {"id": 2}, "score": 18}],
                "players": [
                    {"player": {"id": 11}, "hero": {"localized_name": "Sven"}},
                    {"player": {"id": 22}, "hero": {"localized_name": "Puck"}},
                ],
            }
        ],
    )

    assert scoreboard.games[0].label == "Game 1"
    assert scoreboard.games[0].scores == (31, 18)
    assert scoreboard.players[0].hero_names == ("Sven",)
    assert scoreboard.players[0].value("gpm") == 702
    assert scoreboard.players[0].value("xpm") == 744


def test_scoreboard_renderer_creates_readable_png(navi: EsportsTeam, g2: EsportsTeam) -> None:
    scoreboard = MatchScoreboard(
        match=_match(Game.CS2, navi, g2),
        games=(SeriesGame(position=1, label="Mirage", scores=(13, 8), winner_provider_team_id="1"),),
        players=(
            PlayerMatchStats(
                provider_player_id="11",
                player_name="w0nderful",
                team_provider_id="1",
                hero_names=(),
                statistics=(
                    ("kills", 21),
                    ("deaths", 9),
                    ("assists", 5),
                    ("kast", 82.5),
                    ("adr", 91.4),
                    ("rating", 1.3),
                ),
            ),
            PlayerMatchStats(
                provider_player_id="22",
                player_name="m0NESY",
                team_provider_id="2",
                hero_names=(),
                statistics=(
                    ("kills", 18),
                    ("deaths", 14),
                    ("assists", 4),
                    ("kast", 74.2),
                    ("adr", 85.5),
                    ("rating", 1.17),
                ),
            ),
        ),
    )

    png = ScoreboardRenderer().render(scoreboard)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(png)) as image:
        assert image.width == 1600
        assert image.height >= 900


@dataclass
class PhotoSender:
    events: list[str] = field(default_factory=list)

    async def send_message(self, chat_id: int, text: str) -> object:
        self.events.append("text")
        return object()

    async def send_photo(self, chat_id: int, photo: object) -> object:
        self.events.append("photo")
        return object()


async def test_text_is_sent_before_scoreboard_photo(
    database: Database, navi: EsportsTeam, g2: EsportsTeam
) -> None:
    await GroupRepository(database).upsert(100, "supergroup", "One", is_active=True)
    teams = TeamRepository(database)
    data = _match(Game.CS2, navi, g2)
    stored = await MatchService(teams, MatchRepository(database)).store_finished_match(data)
    tracked = await teams.get_or_create(navi)
    scoreboard = MatchScoreboard(
        match=data,
        games=(SeriesGame(position=1, label="Mirage", scores=(13, 8), winner_provider_team_id="1"),),
        players=(),
    )
    sender = PhotoSender()
    service = NotificationService(NotificationRepository(database), sender)

    assert await service.send_finished_match(100, stored, data, tracked, scoreboard)
    assert sender.events == ["text", "photo"]


async def test_provider_returns_no_scoreboard_when_detailed_plan_is_unavailable(
    navi: EsportsTeam, g2: EsportsTeam
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    client = httpx.AsyncClient(base_url="https://api.pandascore.co", transport=httpx.MockTransport(handler))
    provider = PandaScoreCS2Provider("token", client=client)

    assert await provider.get_match_scoreboard(_match(Game.CS2, navi, g2)) is None
    await client.aclose()
