from __future__ import annotations

from app.database.models import Group
from app.database.repositories.groups import GroupRepository


class GroupService:
    def __init__(self, groups: GroupRepository) -> None:
        self._groups = groups

    async def register(self, chat_id: int, chat_type: str, title: str | None) -> Group:
        return await self._groups.upsert(chat_id, chat_type, title, is_active=True)

    async def mark_inactive(self, chat_id: int) -> None:
        await self._groups.set_active(chat_id, False)
