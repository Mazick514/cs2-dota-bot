from __future__ import annotations

from app.providers.base import Dota2DataProvider
from app.providers.pandascore.cs2 import PandaScoreGameProvider


class PandaScoreDota2Provider(PandaScoreGameProvider, Dota2DataProvider):
    """Async adapter for PandaScore's documented `/dota2/` REST API."""

    _game_path = "dota2"
