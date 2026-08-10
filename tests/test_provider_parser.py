from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.enums import Game, MatchStatus
from app.providers.pandascore.cs2 import PandaScoreCS2Provider, PandaScorePayloadError


def test_parse_documented_pandascore_style_match() -> None:
    payload = {
        "id": 501,
        "status": "finished",
        "begin_at": "2026-08-01T10:00:00Z",
        "end_at": "2026-08-01T12:00:00Z",
        "opponents": [
            {
                "type": "Team",
                "opponent": {"id": 1, "name": "Natus Vincere", "acronym": "NAVI", "slug": "navi"},
            },
            {"type": "Team", "opponent": {"id": 2, "name": "G2 Esports", "acronym": "G2"}},
        ],
        "results": [{"team_id": 1, "score": 2}, {"team_id": 2, "score": 1}],
        "winner": {"id": 1, "type": "Team"},
        "tournament": {"id": 90, "name": "IEM Cologne 2026"},
    }

    match = PandaScoreCS2Provider.parse_match(payload)

    assert match.game is Game.CS2
    assert match.status is MatchStatus.FINISHED
    assert match.opponents[0].acronym == "NAVI"
    assert match.scores == (2, 1)
    assert match.winner_provider_team_id == "1"
    assert match.finished_at == datetime(2026, 8, 1, 12, tzinfo=UTC)


def test_parser_rejects_match_without_two_teams() -> None:
    with pytest.raises(PandaScorePayloadError):
        PandaScoreCS2Provider.parse_match(
            {"id": 1, "status": "finished", "opponents": [], "results": [], "tournament": {}}
        )
