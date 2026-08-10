from __future__ import annotations

import logging

from aiogram import Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMemberUpdated, ErrorEvent, Message

from app.services.groups import GroupService

LOGGER = logging.getLogger(__name__)


def register_common_handlers(router: Router, groups: GroupService) -> None:
    @router.my_chat_member()
    async def on_bot_membership_changed(update: ChatMemberUpdated) -> None:
        if update.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return
        status = getattr(update.new_chat_member.status, "value", update.new_chat_member.status)
        if str(status) in {ChatMemberStatus.LEFT.value, ChatMemberStatus.KICKED.value}:
            await groups.mark_inactive(update.chat.id)
            LOGGER.info("Bot removed from group; group marked inactive", extra={"chat_id": update.chat.id})
            return
        await groups.register(update.chat.id, str(update.chat.type), update.chat.title)
        LOGGER.info("Bot added or updated in group", extra={"chat_id": update.chat.id})

    @router.errors()
    async def on_error(event: ErrorEvent) -> bool:
        LOGGER.exception("Unhandled Telegram update error", exc_info=event.exception)
        if isinstance(event.update.message, Message):
            try:
                await event.update.message.answer("❌ Произошла временная ошибка. Попробуйте ещё раз.")
            except Exception:
                LOGGER.exception("Could not deliver user-facing error")
        return True
