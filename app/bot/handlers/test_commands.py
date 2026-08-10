from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from app.providers.base import DataProviderError, DataProviderRateLimitError, DataProviderTemporaryError
from app.services.groups import GroupService
from app.services.permissions import AdminPermissionService
from app.services.test_mode import TestModeService

LOGGER = logging.getLogger(__name__)


def register_test_command_handlers(
    router: Router,
    *,
    groups: GroupService,
    permissions: AdminPermissionService,
    tests: TestModeService,
) -> None:
    LOGGER.info("Registering administrator test command handlers", extra={"commands": "test_api,test_match"})

    @router.message(Command("test_api"))
    async def test_api_command(message: Message, bot: Bot) -> None:
        LOGGER.info("Test API command handler invoked", extra=_message_log_context(message))
        if not await _ensure_admin(message, bot, groups, permissions):
            return
        LOGGER.info("Test API command administrator check passed", extra=_message_log_context(message))
        try:
            LOGGER.info("Starting PandaScore API diagnostic request", extra=_message_log_context(message))
            result = await tests.check_api()
        except DataProviderRateLimitError:
            LOGGER.warning("PandaScore API diagnostic was rate limited", extra=_message_log_context(message))
            await message.answer("⚠️ PandaScore доступен, но временно ограничил запросы. Повторите позже.")
        except DataProviderTemporaryError:
            LOGGER.warning("PandaScore API diagnostic is temporarily unavailable", extra=_message_log_context(message))
            await message.answer("⚠️ PandaScore временно недоступен. Повторите позже.")
        except DataProviderError:
            LOGGER.warning("PandaScore API diagnostic was rejected", extra=_message_log_context(message))
            await message.answer("❌ PandaScore отклонил запрос. Проверьте доступ ключа и тариф в настройках Railway.")
        except Exception:
            LOGGER.exception("Unexpected PandaScore API diagnostic error", extra=_message_log_context(message))
            await message.answer("❌ Не удалось проверить PandaScore из-за временной внутренней ошибки.")
        else:
            LOGGER.info(
                "PandaScore API diagnostic completed",
                extra={**_message_log_context(message), "match_count": result.match_count},
            )
            await message.answer(
                "✅ PandaScore API доступен.\n"
                f"Найдено завершённых CS2-матчей: <b>{result.match_count}</b>."
            )

    @router.message(Command("test_match"))
    async def test_match_command(message: Message, bot: Bot) -> None:
        LOGGER.info("Test match command handler invoked", extra=_message_log_context(message))
        if not await _ensure_admin(message, bot, groups, permissions):
            return
        LOGGER.info("Test match command administrator check passed", extra=_message_log_context(message))
        try:
            sent_count = await tests.process_test_match(message.chat.id)
        except Exception:
            LOGGER.exception("Test match processing failed", extra={"chat_id": message.chat.id})
            await message.answer("❌ Тестовый матч не удалось обработать. Подробности записаны в журнал приложения.")
            return
        if sent_count:
            await message.answer("✅ Тестовый CS2-матч обработан. Уведомление отправлено через обычный pipeline.")
        else:
            await message.answer("ℹ️ Тестовый матч обработан, но уведомление уже было отправлено ранее.")


async def _ensure_admin(
    message: Message,
    bot: Bot,
    groups: GroupService,
    permissions: AdminPermissionService,
) -> bool:
    context = _message_log_context(message)
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        LOGGER.info("Test command rejected outside a group", extra=context)
        await message.answer("❌ Тестовые команды доступны только администратору группы или супергруппы.")
        return False
    if message.from_user is None:
        LOGGER.warning("Test command has no sender", extra=context)
        return False
    LOGGER.info("Checking test command administrator status", extra=context)
    await groups.register(message.chat.id, str(message.chat.type), message.chat.title)
    try:
        allowed = await permissions.is_group_admin(bot, message.chat.id, message.from_user.id)
    except Exception:
        LOGGER.exception("Could not verify Telegram administrator status for test command", extra=context)
        await message.answer("❌ Не удалось проверить права администратора. Попробуйте ещё раз.")
        return False
    if not allowed:
        LOGGER.info("Test command administrator check denied", extra=context)
        await message.answer("❌ Тестовые команды доступны только администраторам группы.")
        return False
    return True


def _message_log_context(message: Message) -> dict[str, int | str | None]:
    return {
        "chat_id": message.chat.id,
        "chat_type": str(message.chat.type),
        "user_id": message.from_user.id if message.from_user is not None else None,
    }
