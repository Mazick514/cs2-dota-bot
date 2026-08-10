from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import Team
from app.domain.enums import Game
from app.domain.models import EsportsTeam


class CandidateCallback(CallbackData, prefix="teamcandidate"):
    game: str
    action: str
    provider_team_id: str


class RemoveCallback(CallbackData, prefix="teamremove"):
    game: str
    team_id: int


class CancelCallback(CallbackData, prefix="teamcancel"):
    game: str
    action: str


def candidate_keyboard(teams: list[EsportsTeam], game: Game) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for team in teams:
        builder.button(
            text=_team_button_text(team.name, team.acronym),
            callback_data=CandidateCallback(
                game=game.value,
                action="add",
                provider_team_id=team.provider_id,
            ),
        )
    builder.button(
        text="❌ Отмена",
        callback_data=CancelCallback(game=game.value, action="cancel"),
    )
    builder.adjust(1)
    return builder.as_markup()


def confirm_keyboard(team: EsportsTeam, game: Game) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Добавить",
        callback_data=CandidateCallback(
            game=game.value,
            action="add",
            provider_team_id=team.provider_id,
        ),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=CancelCallback(game=game.value, action="cancel"),
    )
    builder.adjust(2)
    return builder.as_markup()


def team_keyboard(teams: list[Team], game: Game) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for team in teams:
        builder.button(
            text=_team_button_text(team.name, team.acronym),
            callback_data=RemoveCallback(game=game.value, team_id=team.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def _team_button_text(name: str, acronym: str | None) -> str:
    return (acronym or name)[:60]
