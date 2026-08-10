from __future__ import annotations

from enum import StrEnum


class Game(StrEnum):
    CS2 = "cs2"
    DOTA2 = "dota2"


class MatchStatus(StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    FINISHED = "finished"
    CANCELED = "canceled"
    POSTPONED = "postponed"
    UNKNOWN = "unknown"


class NotificationType(StrEnum):
    MATCH_FINISHED = "match_finished"
