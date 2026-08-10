from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.database.database import Database
from app.database.models import SentNotification
from app.domain.enums import NotificationType


class NotificationRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def reserve(self, chat_id: int, match_id: int, notification_type: NotificationType) -> bool:
        """Atomically reserve an at-most-once notification before sending it."""
        async with self._database.session() as session:
            session.add(
                SentNotification(
                    chat_id=chat_id,
                    match_id=match_id,
                    notification_type=notification_type.value,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
            return True
