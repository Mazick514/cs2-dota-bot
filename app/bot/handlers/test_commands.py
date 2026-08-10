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
    @router.message(Command("test_api"))
    async def test_api_command(message: Message, bot: Bot) -> None:
        if not await _ensure_admin(message, bot, groups, permissions):
            return
        try:
            result = await tests.check_api()
        except DataProviderRateLimitError:
            await message.answer("⚠️ PandaScore доступен, но временно ограничил запросы. Повторите позже.")
        except DataProviderTemporaryError:
            await message.answer("⚠️ PandaScore временно недоступен. Повторите позже.")
        except DataProviderError:
            await message.answer("❌ PandaScore отклонил запрос. Проверьте доступ ключа и тариф в настройках Railway.")
        except Exception:
            LOGGER.exception("Unexpected PandaScore API diagnostic error")
            await message.answer("❌ Не удалось проверить PandaScore из-за временной внутренней ошибки.")
        else:
            await message.answer(
                "✅ PandaScore API доступен.\n"
                f"Найдено завершённых CS2-матчей: <b>{result.match_count}</b>."
            )

    @router.message(Command("test_match"))
    async def test_match_command(message: Message, bot: Bot) -> None:
        if not await _ensure_admin(message, bot, groups, permissions):
            return
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
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("❌ Тестовые команды доступны только администратору группы или супергруппы.")
        return False
    if message.from_user is None:
        return False
    await groups.register(message.chat.id, str(message.chat.type), message.chat.title)
    try:
        allowed = await permissions.is_group_admin(bot, message.chat.id, message.from_user.id)
    except Exception:
        LOGGER.exception("Could not verify Telegram administrator status for test command")
        await message.answer("❌ Не удалось проверить права администратора. Попробуйте ещё раз.")
        return False
    if not allowed:
        await message.answer("❌ Тестовые команды доступны только администраторам группы.")
        return False
    return True
