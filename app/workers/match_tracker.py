from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.database.repositories.teams import TeamRepository
from app.domain.enums import MatchStatus
from app.domain.models import EsportsMatch, MatchScoreboard
from app.providers.base import EsportsDataProvider
from app.services.matches import MatchService
from app.services.notifications import NotificationService

LOGGER = logging.getLogger(__name__)


class MatchTracker:
    """Independent, graceful async poller for completed tracked-team matches."""

    def __init__(
        self,
        *,
        providers: tuple[EsportsDataProvider, ...],
        teams: TeamRepository,
        matches: MatchService,
        notifications: NotificationService,
        interval_seconds: int,
    ) -> None:
        self._providers = providers
        self._teams = teams
        self._matches = matches
        self._notifications = notifications
        self._interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        LOGGER.info("Starting match tracker", extra={"interval_seconds": self._interval_seconds})
        self._task = asyncio.create_task(self._run(), name="match-tracker")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def run_once(self) -> None:
        for provider in self._providers:
            await self._track_provider(provider)

    async def _track_provider(self, provider: EsportsDataProvider) -> None:
        subscriptions = await self._teams.list_active_subscriptions(provider.game)
        if not subscriptions:
            return
        finished_matches = await provider.get_recent_finished_matches()
        for provider_match in finished_matches:
            if provider_match.status is not MatchStatus.FINISHED:
                continue
            relevant = [
                subscription
                for subscription in subscriptions
                if provider_match.includes_team(subscription.team.provider_team_id)
                and self._finished_after_tracking(provider_match.finished_at, subscription.tracked_at)
            ]
            if not relevant:
                continue
            stored_match = await self._matches.store_finished_match(provider_match)
            scoreboard = await self._load_scoreboard(provider, provider_match)
            for subscription in relevant:
                await self._notifications.send_finished_match(
                    subscription.chat_id,
                    stored_match,
                    provider_match,
                    subscription.team,
                    scoreboard,
                )

    @staticmethod
    async def _load_scoreboard(
        provider: EsportsDataProvider, provider_match: EsportsMatch
    ) -> MatchScoreboard | None:
        try:
            return await provider.get_match_scoreboard(provider_match)
        except Exception:
            LOGGER.exception(
                "Detailed scoreboard lookup failed; continuing with the text notification",
                extra={"game": provider.game.value, "provider_match_id": provider_match.provider_id},
            )
            return None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception:
                LOGGER.exception("Match tracker iteration failed; continuing on the next interval")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                continue

    @staticmethod
    def _finished_after_tracking(finished_at: datetime | None, tracked_at: datetime) -> bool:
        """Do not replay a backlog of historical matches when a team is newly tracked."""
        if finished_at is None:
            return False
        normalized_finished = finished_at.replace(tzinfo=UTC) if finished_at.tzinfo is None else finished_at
        normalized_tracked = tracked_at.replace(tzinfo=UTC) if tracked_at.tzinfo is None else tracked_at
        return normalized_finished >= normalized_tracked
