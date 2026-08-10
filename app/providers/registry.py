from __future__ import annotations

from app.domain.enums import Game
from app.providers.base import EsportsDataProvider


class ProviderRegistry:
    """Explicit provider registry that makes adding Dota 2 a composition change."""

    def __init__(self, providers: list[EsportsDataProvider]) -> None:
        self._providers = {provider.game: provider for provider in providers}

    def for_game(self, game: Game) -> EsportsDataProvider:
        try:
            return self._providers[game]
        except KeyError as exc:
            raise LookupError(f"No provider configured for {game.value}") from exc

    def all(self) -> tuple[EsportsDataProvider, ...]:
        return tuple(self._providers.values())
