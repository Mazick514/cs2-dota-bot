from __future__ import annotations

from _pytest.monkeypatch import MonkeyPatch

from app.config import Settings


def test_legacy_cs2_api_key_environment_variable_is_supported(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("CS2_API_KEY", "legacy-token")
    monkeypatch.delenv("PANDASCORE_API_KEY", raising=False)

    settings = Settings()

    assert settings.pandascore_api_key.get_secret_value() == "legacy-token"
    assert settings.cs2_api_key.get_secret_value() == "legacy-token"


def test_pandascore_api_key_takes_precedence(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("CS2_API_KEY", "legacy-token")
    monkeypatch.setenv("PANDASCORE_API_KEY", "unified-token")

    settings = Settings()

    assert settings.pandascore_api_key.get_secret_value() == "unified-token"
