from __future__ import annotations

import logging
from dataclasses import dataclass
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.teams import (
    CancelCallback,
    CandidateCallback,
    RemoveCallback,
    candidate_keyboard,
    confirm_keyboard,
    team_keyboard,
)
from app.database.models import Team
from app.domain.enums import Game
from app.providers.base import DataProviderError
from app.services.groups import GroupService
from app.services.permissions import AdminPermissionService
from app.services.teams import TeamService, TrackingResult

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TeamCommandSpec:
    game: Game
    display_name: str
    icon: str
    add_command: str
    remove_command: str
    list_command: str
    help_command: str
    settings_command: str
    example_query: str


def register_team_command_handlers(
    router: Router,
    *,
    spec: TeamCommandSpec,
    query_state: State,
    teams: TeamService,
    groups: GroupService,
    permissions: AdminPermissionService,
) -> None:
    """Register the same presentation flow for one game-specific TeamService."""

    @router.message(Command(spec.help_command))
    async def help_command(message: Message) -> None:
        await message.answer(
            f"<b>{spec.display_name} Teams</b>\n\n"
            f"<code>/{spec.add_command} {spec.example_query}</code> — найти и добавить команду\n"
            f"<code>/{spec.add_command}</code> — добавить через диалог\n"
            f"<code>/{spec.remove_command} {spec.example_query}</code> — удалить команду\n"
            f"<code>/{spec.remove_command}</code> — удалить кнопкой\n"
            f"<code>/{spec.list_command}</code> — список отслеживаемых команд\n"
            f"<code>/{spec.settings_command}</code> — статус настроек\n\n"
            "Изменять список могут только администраторы группы."
        )

    @router.message(Command(spec.list_command))
    async def list_command(message: Message) -> None:
        if not _is_group_message(message):
            await message.answer(f"{spec.icon} Список команд доступен в группе или супергруппе Telegram.")
            return
        await groups.register(message.chat.id, str(message.chat.type), message.chat.title)
        tracked = await teams.list_for_chat(message.chat.id)
        if not tracked:
            await message.answer(f"{spec.icon} В этой группе пока нет отслеживаемых {spec.display_name} команд.")
            return
        lines = [f"<b>{spec.icon} Отслеживаемые {spec.display_name} команды:</b>", ""]
        lines.extend(f"{index}. {_team_label(team)}" for index, team in enumerate(tracked, start=1))
        lines.extend(["", f"Всего: {len(tracked)} команд."])
        await message.answer("\n".join(lines))

    @router.message(Command(spec.settings_command))
    async def settings_command(message: Message, bot: Bot) -> None:
        if not await _ensure_admin(message, bot, groups, permissions):
            return
        await message.answer(
            f"<b>⚙️ Настройки {spec.display_name} Teams</b>\n\n"
            "Уведомления о завершённых матчах: <b>включены</b>.\n"
            "Список команд хранится отдельно для этой группы и игры."
        )

    @router.message(Command(spec.add_command))
    async def add_command(
        message: Message,
        command: CommandObject,
        state: FSMContext,
        bot: Bot,
    ) -> None:
        if not await _ensure_admin(message, bot, groups, permissions):
            return
        query = (command.args or "").strip()
        if not query:
            await state.set_state(query_state)
            await message.answer(
                f"Введите название {spec.display_name}-команды, например: <code>{spec.example_query}</code>."
            )
            return
        await _show_search_results(message, query, teams, spec)

    @router.message(StateFilter(query_state))
    async def receive_team_query(message: Message, state: FSMContext, bot: Bot) -> None:
        if not await _ensure_admin(message, bot, groups, permissions):
            await state.clear()
            return
        await state.clear()
        query = (message.text or "").strip()
        if not query:
            await message.answer(
                f"❌ Название команды не может быть пустым. Повторите <code>/{spec.add_command}</code>."
            )
            return
        await _show_search_results(message, query, teams, spec)

    @router.callback_query(CandidateCallback.filter(F.game == spec.game.value))
    async def add_candidate(callback: CallbackQuery, callback_data: CandidateCallback, bot: Bot) -> None:
        if callback_data.action != "add":
            await callback.answer()
            return
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer("Это сообщение больше недоступно.", show_alert=True)
            return
        if not await _ensure_callback_admin(callback, bot, groups, permissions):
            return
        try:
            outcome = await teams.add_by_provider_id(callback.message.chat.id, callback_data.provider_team_id)
        except DataProviderError:
            LOGGER.exception("Provider failed while adding team", extra={"game": spec.game.value})
            await callback.answer("Источник esports-данных временно недоступен.", show_alert=True)
            return
        except Exception:
            LOGGER.exception("Failed to add team", extra={"game": spec.game.value})
            await callback.answer("Не удалось добавить команду. Попробуйте ещё раз.", show_alert=True)
            return
        await callback.answer()
        if outcome.result is TrackingResult.ALREADY_TRACKED:
            text = f"ℹ️ Команда <b>{escape(outcome.team.name)}</b> уже отслеживается в этой группе."
        else:
            text = f"✅ Команда <b>{escape(outcome.team.name)}</b> добавлена в отслеживание этой группы."
        await callback.message.edit_text(text)

    @router.message(Command(spec.remove_command))
    async def remove_command(message: Message, command: CommandObject, bot: Bot) -> None:
        if not await _ensure_admin(message, bot, groups, permissions):
            return
        query = (command.args or "").strip()
        if not query:
            tracked = await teams.list_for_chat(message.chat.id)
            if not tracked:
                await message.answer(f"{spec.icon} В этой группе пока нет отслеживаемых {spec.display_name} команд.")
                return
            await message.answer(
                "Выберите команду для удаления:",
                reply_markup=team_keyboard(tracked, spec.game),
            )
            return
        candidates = await teams.remove_by_query(message.chat.id, query)
        if not candidates:
            await message.answer("❌ Эта команда не отслеживается в данной группе.")
            return
        if len(candidates) > 1:
            await message.answer(
                "Найдено несколько команд. Выберите нужную:",
                reply_markup=team_keyboard(candidates, spec.game),
            )
            return
        removed = await teams.remove_by_local_id(message.chat.id, candidates[0].id)
        if removed is None:
            await message.answer("❌ Эта команда не отслеживается в данной группе.")
            return
        await message.answer(f"✅ <b>{escape(removed.name)}</b> удалена из отслеживания.")

    @router.callback_query(RemoveCallback.filter(F.game == spec.game.value))
    async def remove_candidate(callback: CallbackQuery, callback_data: RemoveCallback, bot: Bot) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer("Это сообщение больше недоступно.", show_alert=True)
            return
        if not await _ensure_callback_admin(callback, bot, groups, permissions):
            return
        removed = await teams.remove_by_local_id(callback.message.chat.id, callback_data.team_id)
        await callback.answer()
        if removed is None:
            await callback.message.edit_text("❌ Эта команда уже не отслеживается в данной группе.")
            return
        await callback.message.edit_text(f"✅ <b>{escape(removed.name)}</b> удалена из отслеживания.")

    @router.callback_query(CancelCallback.filter(F.game == spec.game.value))
    async def cancel_action(callback: CallbackQuery, callback_data: CancelCallback, state: FSMContext) -> None:
        if callback_data.action != "cancel":
            await callback.answer()
            return
        await state.clear()
        await callback.answer("Отменено")
        if callback.message is not None and isinstance(callback.message, Message):
            await callback.message.edit_text("❌ Действие отменено.")


async def _show_search_results(
    message: Message,
    query: str,
    teams: TeamService,
    spec: TeamCommandSpec,
) -> None:
    try:
        found = await teams.search(query)
    except DataProviderError:
        LOGGER.exception("Provider failed while searching teams", extra={"game": spec.game.value})
        await message.answer("❌ Источник esports-данных временно недоступен. Попробуйте позже.")
        return
    if not found:
        await message.answer("❌ Команда не найдена. Проверьте название и попробуйте ещё раз.")
        return
    if len(found) == 1:
        team = found[0]
        await message.answer(
            f"🔎 Найдена команда: <b>{escape(team.name)}</b>. Добавить её?",
            reply_markup=confirm_keyboard(team, spec.game),
        )
        return
    lines = ["<b>🔎 Найдены команды:</b>", ""]
    lines.extend(f"• {escape(team.name)}" for team in found)
    await message.answer("\n".join(lines), reply_markup=candidate_keyboard(found, spec.game))


async def _ensure_admin(
    message: Message,
    bot: Bot,
    groups: GroupService,
    permissions: AdminPermissionService,
) -> bool:
    if not _is_group_message(message):
        await message.answer("❌ Управлять командами можно только в группе или супергруппе.")
        return False
    if message.from_user is None:
        return False
    await groups.register(message.chat.id, str(message.chat.type), message.chat.title)
    try:
        allowed = await permissions.is_group_admin(bot, message.chat.id, message.from_user.id)
    except Exception:
        LOGGER.exception("Could not verify Telegram administrator status")
        await message.answer("❌ Не удалось проверить права администратора. Попробуйте ещё раз.")
        return False
    if not allowed:
        await message.answer("❌ Изменять список команд могут только администраторы группы.")
        return False
    return True


async def _ensure_callback_admin(
    callback: CallbackQuery,
    bot: Bot,
    groups: GroupService,
    permissions: AdminPermissionService,
) -> bool:
    if callback.message is None or not isinstance(callback.message, Message):
        await callback.answer("Это сообщение больше недоступно.", show_alert=True)
        return False
    message = callback.message
    if not _is_group_message(message):
        await callback.answer("Управлять командами можно только в группе.", show_alert=True)
        return False
    await groups.register(message.chat.id, str(message.chat.type), message.chat.title)
    try:
        allowed = await permissions.is_group_admin(bot, message.chat.id, callback.from_user.id)
    except Exception:
        LOGGER.exception("Could not verify Telegram administrator status for callback")
        await callback.answer("Не удалось проверить права администратора.", show_alert=True)
        return False
    if not allowed:
        await callback.answer("Изменять список могут только администраторы группы.", show_alert=True)
        return False
    return True


def _is_group_message(message: Message) -> bool:
    return message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}


def _team_label(team: Team) -> str:
    label = escape(team.name)
    return f"<b>{label}</b>" if team.acronym is None else f"<b>{escape(team.acronym)}</b> — {label}"
