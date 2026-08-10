from __future__ import annotations

from typing import Protocol


class ChatMemberLike(Protocol):
    @property
    def status(self) -> object: ...


class TelegramAdminGateway(Protocol):
    async def get_chat_member(
        self,
        chat_id: int | str,
        user_id: int,
        request_timeout: int | None = None,
    ) -> ChatMemberLike: ...


def is_admin_status(status: object) -> bool:
    """Accept both current and legacy Bot API owner status spellings."""
    value = getattr(status, "value", status)
    return str(value).casefold() in {"administrator", "creator", "owner"}


class AdminPermissionService:
    async def is_group_admin(self, bot: TelegramAdminGateway, chat_id: int, user_id: int) -> bool:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return is_admin_status(member.status)
