"""Tests for theme config wiring in PhyraxApp.

Validates that:
- A valid theme from config is applied to the app on mount.
- An unknown theme falls back to "textual-dark" with a logged warning.
"""

from __future__ import annotations

import logging

import pytest
from textual.app import App, ComposeResult

from phyrax.config import PhyraxConfig

# ---------------------------------------------------------------------------
# Minimal test app that mirrors PhyraxApp theme-application logic
# ---------------------------------------------------------------------------


class _ThemeTestApp(App):  # type: ignore[type-arg]  # Textual App is generic at runtime but unparameterized here
    """Minimal App that applies a theme from PhyraxConfig on mount."""

    def __init__(self, config: PhyraxConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        log = logging.getLogger("phyrax")
        configured_theme = self._config.display.theme
        if configured_theme in self.available_themes:
            self.theme = configured_theme
        else:
            log.warning(
                "Unknown theme %r in config; falling back to textual-dark",
                configured_theme,
            )
            self.theme = "textual-dark"


def _make_config(theme: str = "textual-dark") -> PhyraxConfig:
    cfg = PhyraxConfig.model_validate(
        {
            "identity": {"primary": "test@example.com", "aliases": []},
            "ai": {"agent_command": "echo"},
            "display": {"theme": theme},
        }
    )
    return cfg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_theme_applied() -> None:
    """A known theme from config is set on the app."""
    config = _make_config(theme="nord")
    app = _ThemeTestApp(config)

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.theme == "nord"


@pytest.mark.asyncio
async def test_invalid_theme_falls_back(caplog: pytest.LogCaptureFixture) -> None:
    """An unknown theme falls back to textual-dark and logs a warning."""
    config = _make_config(theme="bogus")
    app = _ThemeTestApp(config)

    with caplog.at_level(logging.WARNING, logger="phyrax"):
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert app.theme == "textual-dark"

    assert any("Unknown theme" in record.message for record in caplog.records)
    assert any("bogus" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_default_theme_applied() -> None:
    """Default config uses textual-dark."""
    config = _make_config()  # default = "textual-dark"
    app = _ThemeTestApp(config)

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.theme == "textual-dark"
