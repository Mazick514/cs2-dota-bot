from __future__ import annotations

from app.database.database import Database
from app.database.models import Group


class GroupRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def upsert(self, chat_id: int, chat_type: str, title: str | None, *, is_active: bool) -> Group:
        async with self._database.session() as session:
            group = await session.get(Group, chat_id)
            if group is None:
                group = Group(chat_id=chat_id, chat_type=chat_type, title=title, is_active=is_active)
                session.add(group)
            else:
                group.chat_type = chat_type
                group.title = title
                group.is_active = is_active
            await session.commit()
            return group

    async def set_active(self, chat_id: int, is_active: bool) -> None:
        async with self._database.session() as session:
            group = await session.get(Group, chat_id)
            if group is not None:
                group.is_active = is_active
                await session.commit()
