from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import (
    register_common_handlers,
    register_cs2_team_handlers,
    register_dota2_team_handlers,
    register_test_command_handlers,
)
from app.config import Settings
from app.database.database import Database
from app.database.repositories import (
    GroupRepository,
    MatchRepository,
    NotificationRepository,
    TeamRepository,
)
from app.domain.enums import Game
from app.providers.pandascore import PandaScoreCS2Provider, PandaScoreDota2Provider
from app.providers.registry import ProviderRegistry
from app.services import (
    AdminPermissionService,
    GroupService,
    MatchService,
    NotificationService,
    TeamService,
    TestModeService,
)
from app.workers import MatchTracker


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


async def run() -> None:
    settings = Settings()  # type: ignore[call-arg]  # Values are read dynamically from .env/environment.
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    logger.info("Starting combined CS2 and Dota 2 Teams Bot application")

    database = Database(settings.database_url)
    await database.create_schema()
    logger.info("Database connected and schema verified")

    api_key = settings.pandascore_api_key.get_secret_value()
    cs2_provider = PandaScoreCS2Provider(api_key)
    dota2_provider = PandaScoreDota2Provider(api_key)
    providers = ProviderRegistry([cs2_provider, dota2_provider])
    groups_repository = GroupRepository(database)
    teams_repository = TeamRepository(database)
    matches_repository = MatchRepository(database)
    notifications_repository = NotificationRepository(database)

    group_service = GroupService(groups_repository)
    cs2_team_service = TeamService(teams_repository, providers.for_game(Game.CS2), Game.CS2)
    dota2_team_service = TeamService(teams_repository, providers.for_game(Game.DOTA2), Game.DOTA2)
    match_service = MatchService(teams_repository, matches_repository)
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    notification_service = NotificationService(notifications_repository, bot)
    tracker = MatchTracker(
        providers=providers.all(),
        teams=teams_repository,
        matches=match_service,
        notifications=notification_service,
        interval_seconds=settings.match_poll_interval_seconds,
    )

    dispatcher = Dispatcher()
    register_common_handlers(dispatcher, group_service)
    register_test_command_handlers(
        dispatcher,
        groups=group_service,
        permissions=AdminPermissionService(),
        tests=TestModeService(cs2_provider=cs2_provider, teams=teams_repository, tracker=tracker),
    )
    register_cs2_team_handlers(
        dispatcher,
        teams=cs2_team_service,
        groups=group_service,
        permissions=AdminPermissionService(),
    )
    register_dota2_team_handlers(
        dispatcher,
        teams=dota2_team_service,
        groups=group_service,
        permissions=AdminPermissionService(),
    )

    await tracker.start()
    logger.info("Telegram bot polling started")
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        logger.info("Stopping combined CS2 and Dota 2 Teams Bot application")
        await tracker.stop()
        for provider in providers.all():
            await provider.aclose()
        await bot.session.close()
        await database.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
