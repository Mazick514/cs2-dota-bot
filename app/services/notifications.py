from __future__ import annotations

import logging
from html import escape
from typing import Protocol

from aiogram.types import BufferedInputFile

from app.database.models import Match, Team
from app.database.repositories.notifications import NotificationRepository
from app.domain.enums import NotificationType
from app.domain.models import EsportsMatch, MatchScoreboard
from app.renderers import ScoreboardRenderer

LOGGER = logging.getLogger(__name__)


class TelegramMessageSender(Protocol):
    async def send_message(self, chat_id: int, text: str) -> object: ...

    async def send_photo(self, chat_id: int, photo: BufferedInputFile) -> object: ...


class NotificationService:
    """Persists the de-duplication key before the Telegram side effect (at-most-once)."""

    def __init__(
        self,
        repository: NotificationRepository,
        sender: TelegramMessageSender,
        renderer: ScoreboardRenderer | None = None,
    ) -> None:
        self._repository = repository
        self._sender = sender
        self._renderer = renderer or ScoreboardRenderer()

    async def send_finished_match(
        self,
        chat_id: int,
        match: Match,
        data: EsportsMatch,
        tracked: Team,
        scoreboard: MatchScoreboard | None = None,
    ) -> bool:
        if not await self._repository.reserve(chat_id, match.id, NotificationType.MATCH_FINISHED):
            return False
        try:
            await self._sender.send_message(chat_id=chat_id, text=self._finished_text(data, tracked))
        except Exception:
            # The durable reservation intentionally remains: with an unknown network
            # outcome, retrying could violate the no-duplicate notification guarantee.
            LOGGER.exception("Unable to send finished-match notification", extra={"chat_id": chat_id})
            return False
        if scoreboard is not None:
            await self._send_scoreboard(chat_id, match.id, scoreboard)
        LOGGER.info("Finished-match notification sent", extra={"chat_id": chat_id, "match_id": match.id})
        return True

    async def _send_scoreboard(self, chat_id: int, match_id: int, scoreboard: MatchScoreboard) -> None:
        """A statistics image is an enhancement, never a reason to lose the result message."""

        try:
            image = self._renderer.render(scoreboard)
            await self._sender.send_photo(
                chat_id=chat_id,
                photo=BufferedInputFile(image, filename=f"scoreboard-{scoreboard.match.game.value}-{match_id}.png"),
            )
        except Exception:
            LOGGER.exception(
                "Unable to render or send detailed scoreboard; the text result was still delivered",
                extra={"chat_id": chat_id, "match_id": match_id, "game": scoreboard.match.game.value},
            )

    @staticmethod
    def _finished_text(match: EsportsMatch, tracked: Team) -> str:
        first, second = match.opponents
        first_score, second_score = match.scores
        tracked_won = match.winner_provider_team_id == tracked.provider_team_id
        if match.winner_provider_team_id is None:
            result = "ЗАВЕРШИЛИ МАТЧ"
            icon = "🏁"
        elif tracked_won:
            result = "ПОБЕДИЛИ"
            icon = "🏆"
        else:
            result = "ПРОИГРАЛИ"
            icon = "❌"
        first_name = escape(first.acronym or first.name)
        second_name = escape(second.acronym or second.name)
        tournament = escape(match.tournament_name or "Турнир не указан")
        return (
            f"{icon} <b>{escape(tracked.name)} {result}</b>\n\n"
            f"<b>{first_name} {first_score if first_score is not None else '—'} : "
            f"{second_score if second_score is not None else '—'} {second_name}</b>\n\n"
            f"🏆 {tournament}\n\n"
            "Матч завершён."
        )
