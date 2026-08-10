from __future__ import annotations

from aiogram import Router
from aiogram.fsm.state import State, StatesGroup

from app.bot.handlers.team_commands import TeamCommandSpec, register_team_command_handlers
from app.domain.enums import Game
from app.services.groups import GroupService
from app.services.permissions import AdminPermissionService
from app.services.teams import TeamService


class CS2AddTeamState(StatesGroup):
    waiting_for_query = State()


def register_cs2_team_handlers(
    router: Router,
    *,
    teams: TeamService,
    groups: GroupService,
    permissions: AdminPermissionService,
) -> None:
    register_team_command_handlers(
        router,
        spec=TeamCommandSpec(
            game=Game.CS2,
            display_name="CS2",
            icon="🎮",
            add_command="csaddteam",
            remove_command="csremoveteam",
            list_command="csteams",
            help_command="cshelp",
            settings_command="cssettings",
            example_query="NAVI",
        ),
        query_state=CS2AddTeamState.waiting_for_query,
        teams=teams,
        groups=groups,
        permissions=permissions,
    )
