from __future__ import annotations

from aiogram import Router
from aiogram.fsm.state import State, StatesGroup

from app.bot.handlers.team_commands import TeamCommandSpec, register_team_command_handlers
from app.domain.enums import Game
from app.services.groups import GroupService
from app.services.permissions import AdminPermissionService
from app.services.teams import TeamService


class Dota2AddTeamState(StatesGroup):
    waiting_for_query = State()


def register_dota2_team_handlers(
    router: Router,
    *,
    teams: TeamService,
    groups: GroupService,
    permissions: AdminPermissionService,
) -> None:
    register_team_command_handlers(
        router,
        spec=TeamCommandSpec(
            game=Game.DOTA2,
            display_name="Dota 2",
            icon="🛡️",
            add_command="dotaaddteam",
            remove_command="dotaremoveteam",
            list_command="dotateams",
            help_command="dotahelp",
            settings_command="dotasettings",
            example_query="Spirit",
        ),
        query_state=Dota2AddTeamState.waiting_for_query,
        teams=teams,
        groups=groups,
        permissions=permissions,
    )
