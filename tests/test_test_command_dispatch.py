from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, SendMessage
from aiogram.methods.base import TelegramMethod
from aiogram.types import Update, User

from app.bot.handlers.test_commands import register_test_command_handlers
from app.services.test_mode import ApiCheckResult


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.sent_messages: list[SendMessage] = []

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> Any:
        if isinstance(method, GetMe):
            return User(id=42, is_bot=True, first_name="Test Bot", username="cs2_news_fofriend_bot")
        if isinstance(method, SendMessage):
            self.sent_messages.append(method)
        return True

    async def close(self) -> None:
        return None

    async def stream_content(
        self,
        url: str,
        timeout: int,  # noqa: ASYNC109
        chunk_size: int,
        raise_for_status: bool,
    ) -> Any:
        if False:
            yield b""


@dataclass
class FakeGroups:
    registrations: list[tuple[int, str, str | None]] = field(default_factory=list)

    async def register(self, chat_id: int, chat_type: str, title: str | None) -> object:
        self.registrations.append((chat_id, chat_type, title))
        return object()


class FakePermissions:
    async def is_group_admin(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        return True


class FakeTests:
    async def check_api(self) -> ApiCheckResult:
        return ApiCheckResult(match_count=7)

    async def process_test_match(self, chat_id: int) -> int:
        return 0


async def test_test_api_group_command_with_bot_mention_is_dispatched() -> None:
    session = RecordingSession()
    bot = Bot(token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=session)
    dispatcher = Dispatcher()
    groups = FakeGroups()
    register_test_command_handlers(
        dispatcher,
        groups=groups,  # type: ignore[arg-type]
        permissions=FakePermissions(),  # type: ignore[arg-type]
        tests=FakeTests(),  # type: ignore[arg-type]
    )
    update = Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 0,
                "chat": {"id": -100, "type": "supergroup", "title": "Tests"},
                "from": {"id": 1, "is_bot": False, "first_name": "Admin"},
                "text": "/test_api@cs2_news_fofriend_bot",
                "entities": [{"type": "bot_command", "offset": 0, "length": 32}],
            },
        },
        context={"bot": bot},
    )

    await dispatcher.feed_update(bot, update)

    assert groups.registrations == [(-100, "supergroup", "Tests")]
    assert [message.text for message in session.sent_messages] == [
        "✅ PandaScore API доступен.\nНайдено завершённых CS2-матчей: <b>7</b>."
    ]
    await bot.session.close()
