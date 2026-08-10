from app.bot.handlers.common import register_common_handlers
from app.bot.handlers.cs2_teams import register_cs2_team_handlers
from app.bot.handlers.dota2_teams import register_dota2_team_handlers

__all__ = ["register_common_handlers", "register_cs2_team_handlers", "register_dota2_team_handlers"]
