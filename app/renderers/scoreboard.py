from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.domain.enums import Game
from app.domain.models import MatchScoreboard, PlayerMatchStats, StatisticValue


class ScoreboardRenderer:
    """Builds a phone-readable PNG from normalized match statistics.

    It intentionally has no knowledge of PandaScore, Telegram, HLTV, or HTML. The
    provider is responsible for normalizing data and the notification service is
    responsible for delivery.
    """

    _WIDTH = 1600
    _MARGIN = 56
    _BACKGROUND = "#0C1222"
    _PANEL = "#151F34"
    _PANEL_ALT = "#1B2842"
    _TEXT = "#F4F7FB"
    _MUTED = "#9CABBF"
    _LEFT_ACCENT = "#4CA8FF"
    _RIGHT_ACCENT = "#F4B84A"

    def render(self, scoreboard: MatchScoreboard) -> bytes:
        """Return a lossless PNG suitable for `sendPhoto` without a temp file."""

        first_team, second_team = scoreboard.match.opponents
        left_players = self._players_for(scoreboard, first_team.provider_id)
        right_players = self._players_for(scoreboard, second_team.provider_id)
        game_rows = max(1, (len(scoreboard.games) + 2) // 3)
        player_rows = max(len(left_players), len(right_players), 1)
        height = max(900, 330 + game_rows * 112 + 105 + player_rows * 78 + 74)
        image = Image.new("RGB", (self._WIDTH, height), self._BACKGROUND)
        draw = ImageDraw.Draw(image)
        fonts = self._fonts()

        self._draw_header(draw, scoreboard, fonts)
        games_bottom = self._draw_games(draw, scoreboard, 242, fonts)
        table_top = games_bottom + 30
        self._draw_player_tables(draw, scoreboard, left_players, right_players, table_top, fonts)
        self._draw_footer(draw, height, fonts)

        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()

    def _draw_header(self, draw: Any, scoreboard: MatchScoreboard, fonts: dict[str, Any]) -> None:
        match = scoreboard.match
        first, second = match.opponents
        first_score, second_score = match.scores
        game_title = "COUNTER-STRIKE 2" if match.game is Game.CS2 else "DOTA 2"
        tournament = match.tournament_name or "Tournament not specified"

        draw.rounded_rectangle((self._MARGIN, 38, self._WIDTH - self._MARGIN, 212), radius=26, fill=self._PANEL)
        draw.text((self._MARGIN + 32, 66), game_title, fill=self._MUTED, font=fonts["small"])
        self._centered(draw, tournament, 96, fonts["title"], self._TEXT)
        team_line = (
            f"{first.acronym or first.name}   {self._score(first_score)} : {self._score(second_score)}   "
            f"{second.acronym or second.name}"
        )
        self._centered(draw, team_line, 151, fonts["score"], self._TEXT)
        draw.rounded_rectangle((self._MARGIN + 32, 187, self._MARGIN + 160, 195), radius=4, fill=self._LEFT_ACCENT)
        draw.rounded_rectangle(
            (self._WIDTH - self._MARGIN - 160, 187, self._WIDTH - self._MARGIN - 32, 195),
            radius=4,
            fill=self._RIGHT_ACCENT,
        )

    def _draw_games(self, draw: Any, scoreboard: MatchScoreboard, top: int, fonts: dict[str, Any]) -> int:
        is_cs2 = scoreboard.match.game is Game.CS2
        title = "MAP RESULTS" if is_cs2 else "GAME RESULTS"
        draw.text((self._MARGIN, top), title, fill=self._MUTED, font=fonts["small"])
        card_top = top + 34
        gap = 18
        card_width = (self._WIDTH - self._MARGIN * 2 - gap * 2) // 3
        card_height = 92
        for index, game in enumerate(scoreboard.games):
            row, column = divmod(index, 3)
            left = self._MARGIN + column * (card_width + gap)
            y = card_top + row * (card_height + 18)
            winner = game.winner_provider_team_id
            first, second = scoreboard.match.opponents
            accent = self._LEFT_ACCENT if winner == first.provider_id else self._RIGHT_ACCENT
            if winner is None:
                accent = self._MUTED
            draw.rounded_rectangle((left, y, left + card_width, y + card_height), radius=18, fill=self._PANEL_ALT)
            draw.rounded_rectangle((left, y, left + 8, y + card_height), radius=4, fill=accent)
            label = self._fit(draw, game.label, fonts["body"], card_width - 64)
            draw.text((left + 30, y + 18), label, fill=self._TEXT, font=fonts["body"])
            score = f"{self._score(game.scores[0])} : {self._score(game.scores[1])}"
            draw.text((left + 30, y + 50), score, fill=self._MUTED, font=fonts["body"])
        rows = max(1, (len(scoreboard.games) + 2) // 3)
        return card_top + rows * card_height + max(0, rows - 1) * 18

    def _draw_player_tables(
        self,
        draw: Any,
        scoreboard: MatchScoreboard,
        left_players: tuple[PlayerMatchStats, ...],
        right_players: tuple[PlayerMatchStats, ...],
        top: int,
        fonts: dict[str, Any],
    ) -> None:
        first, second = scoreboard.match.opponents
        gap = 22
        panel_width = (self._WIDTH - self._MARGIN * 2 - gap) // 2
        self._draw_team_table(
            draw,
            scoreboard,
            left_players,
            first.acronym or first.name,
            self._MARGIN,
            top,
            panel_width,
            self._LEFT_ACCENT,
            fonts,
        )
        self._draw_team_table(
            draw,
            scoreboard,
            right_players,
            second.acronym or second.name,
            self._MARGIN + panel_width + gap,
            top,
            panel_width,
            self._RIGHT_ACCENT,
            fonts,
        )

    def _draw_team_table(
        self,
        draw: Any,
        scoreboard: MatchScoreboard,
        players: tuple[PlayerMatchStats, ...],
        team_name: str,
        left: int,
        top: int,
        width: int,
        accent: str,
        fonts: dict[str, Any],
    ) -> None:
        row_height = 78
        height = 94 + max(len(players), 1) * row_height
        draw.rounded_rectangle((left, top, left + width, top + height), radius=22, fill=self._PANEL)
        draw.rounded_rectangle((left, top, left + width, top + 9), radius=4, fill=accent)
        draw.text(
            (left + 24, top + 25),
            self._fit(draw, team_name, fonts["body"], width - 48),
            fill=self._TEXT,
            font=fonts["body"],
        )

        columns = self._columns(scoreboard.match.game)
        name_width = 135 if scoreboard.match.game is Game.CS2 else 112
        hero_width = 0 if scoreboard.match.game is Game.CS2 else 128
        metrics_left = left + 22 + name_width + hero_width
        metric_width = max(52, (width - 44 - name_width - hero_width) // len(columns))
        header_y = top + 59
        draw.text((left + 22, header_y), "PLAYER", fill=self._MUTED, font=fonts["tiny"])
        if hero_width:
            draw.text((left + 22 + name_width, header_y), "HEROES", fill=self._MUTED, font=fonts["tiny"])
        for index, (label, _) in enumerate(columns):
            self._centered_in(
                draw,
                label,
                metrics_left + index * metric_width,
                metric_width,
                header_y,
                fonts["tiny"],
                self._MUTED,
            )

        for index, player in enumerate(players):
            y = top + 92 + index * row_height
            if index % 2 == 0:
                draw.rounded_rectangle(
                    (left + 12, y - 4, left + width - 12, y + row_height - 5),
                    radius=12,
                    fill=self._PANEL_ALT,
                )
            name = self._fit(draw, player.player_name, fonts["body"], name_width - 12)
            draw.text((left + 22, y + 8), name, fill=self._TEXT, font=fonts["body"])
            if hero_width:
                hero_text = self._fit(draw, " / ".join(player.hero_names) or "—", fonts["tiny"], hero_width - 10)
                draw.text((left + 22 + name_width, y + 11), hero_text, fill=self._MUTED, font=fonts["tiny"])
            for column_index, (_, key) in enumerate(columns):
                self._centered_in(
                    draw,
                    self._format_stat(player.value(key), key),
                    metrics_left + column_index * metric_width,
                    metric_width,
                    y + 8,
                    fonts["body"],
                    self._TEXT,
                )
            extra = self._fit(draw, self._extra_statistics(scoreboard.match.game, player), fonts["tiny"], width - 44)
            draw.text((left + 22, y + 43), extra, fill=self._MUTED, font=fonts["tiny"])

    def _draw_footer(self, draw: Any, height: int, fonts: dict[str, Any]) -> None:
        self._centered(draw, "Detailed match data provided by PandaScore", height - 44, fonts["tiny"], self._MUTED)

    @staticmethod
    def _players_for(scoreboard: MatchScoreboard, team_id: str) -> tuple[PlayerMatchStats, ...]:
        return tuple(player for player in scoreboard.players if player.team_provider_id == team_id)

    @staticmethod
    def _columns(game: Game) -> tuple[tuple[str, str], ...]:
        if game is Game.CS2:
            return (
                ("K", "kills"),
                ("D", "deaths"),
                ("A", "assists"),
                ("KAST", "kast"),
                ("ADR", "adr"),
                ("RTG", "rating"),
            )
        return (("K", "kills"), ("D", "deaths"), ("A", "assists"), ("GPM", "gpm"), ("XPM", "xpm"))

    @staticmethod
    def _extra_statistics(game: Game, player: PlayerMatchStats) -> str:
        keys = (
            (
                ("HS", "headshots"),
                ("K-D", "k_d_diff"),
                ("FKΔ", "first_kills_diff"),
                ("FA", "flash_assists"),
                ("Cl", "clutch_rounds_won"),
                ("MK", "multi_kills"),
                ("UK", "utility_kills"),
            )
            if game is Game.CS2
            else (
                ("LH", "last_hits"),
                ("DN", "denies"),
                ("HD", "hero_damage"),
                ("TD", "tower_damage"),
                ("KP", "kill_participation"),
                ("W", "wards_placed"),
            )
        )
        parts = [
            f"{label} {ScoreboardRenderer._format_stat(player.value(key), key)}"
            for label, key in keys
            if player.value(key) is not None
        ]
        return "  ·  ".join(parts) or "No additional player statistics"

    @staticmethod
    def _format_stat(value: StatisticValue | None, key: str) -> str:
        if value is None:
            return "—"
        if isinstance(value, float):
            if key in {"kast", "kill_participation"}:
                return f"{value:.1f}%"
            if key in {"adr", "rating"}:
                return f"{value:.2f}" if key == "rating" else f"{value:.1f}"
            return f"{value:.1f}" if not value.is_integer() else str(int(value))
        if key == "first_kills_diff" and isinstance(value, (int, float)) and value > 0:
            return f"+{value}"
        return str(value)

    @staticmethod
    def _score(value: int | None) -> str:
        return str(value) if value is not None else "—"

    @staticmethod
    def _font_path() -> Path | None:
        candidates = (
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        )
        return next((path for path in candidates if path.exists()), None)

    def _fonts(self) -> dict[str, Any]:
        path = self._font_path()
        if path is None:
            fallback = ImageFont.load_default()
            return {"title": fallback, "score": fallback, "body": fallback, "small": fallback, "tiny": fallback}
        return {
            "title": ImageFont.truetype(str(path), 32),
            "score": ImageFont.truetype(str(path), 42),
            "body": ImageFont.truetype(str(path), 24),
            "small": ImageFont.truetype(str(path), 19),
            "tiny": ImageFont.truetype(str(path), 15),
        }

    @staticmethod
    def _fit(draw: Any, text: str, font: Any, max_width: int) -> str:
        if draw.textlength(text, font=font) <= max_width:
            return text
        suffix = "…"
        shortened = text
        while shortened and draw.textlength(shortened + suffix, font=font) > max_width:
            shortened = shortened[:-1]
        return shortened + suffix if shortened else suffix

    def _centered(self, draw: Any, text: str, y: int, font: Any, fill: str) -> None:
        self._centered_in(draw, text, 0, self._WIDTH, y, font, fill)

    @staticmethod
    def _centered_in(draw: Any, text: str, left: int, width: int, y: int, font: Any, fill: str) -> None:
        x = left + (width - draw.textlength(text, font=font)) / 2
        draw.text((x, y), text, fill=fill, font=font)
