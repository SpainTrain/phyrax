"""Tests for theme-switcher commands in CommandPalette and ThemeSelector.

Covers:
- CommandPalette contains "Next theme" and "Select theme..." entries.
- "Next theme" cycles app.theme forward and persists via config.
- "Select theme..." pushes ThemeSelector; selecting a theme applies and persists it.
- ThemeSelector lists all available_themes (current one at top).
- Escape from ThemeSelector cancels without changing theme.
- _apply_theme ignores unknown theme names.
- _apply_next_theme wraps around at the end of the list.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from phyrax.config import PhyraxConfig
from phyrax.tui.widgets.command_palette import (
    CommandPalette,
    _apply_next_theme,
    _apply_theme,
)
from phyrax.tui.widgets.theme_selector import ThemeSelector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(theme: str = "textual-dark") -> PhyraxConfig:
    return PhyraxConfig.model_validate(
        {
            "identity": {"primary": "test@example.com", "aliases": []},
            "ai": {"agent_command": "echo"},
            "display": {"theme": theme},
        }
    )


class _PaletteApp(App):  # type: ignore[type-arg]
    """Minimal App that pushes CommandPalette directly on mount."""

    def __init__(self, config: PhyraxConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(CommandPalette(self._config))


class _SelectorApp(App):  # type: ignore[type-arg]
    """Minimal App that pushes ThemeSelector directly on mount."""

    def __init__(self, config: PhyraxConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(ThemeSelector(self._config))


# ---------------------------------------------------------------------------
# CommandPalette entry list tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_palette_contains_theme_entries() -> None:
    """CommandPalette entry list includes 'Next theme' and 'Select theme...'."""
    config = _make_config()
    app = _PaletteApp(config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        palette = app.screen
        assert isinstance(palette, CommandPalette)

        entry_names = [e.name for e in palette._all_entries]
        assert "Next theme" in entry_names
        assert "Select theme\u2026" in entry_names


@pytest.mark.asyncio
async def test_palette_theme_entries_visible_in_list_view() -> None:
    """Both theme entries appear as ListItems in the palette ListView."""
    from textual.widgets import ListItem

    config = _make_config()
    app = _PaletteApp(config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        palette = app.screen
        assert isinstance(palette, CommandPalette)

        lv = palette.query_one("#entry-list")
        items = list(lv.query(ListItem))
        # The ListView should have one item per entry in _filtered (which starts
        # as all _all_entries).  Theme entries bring the total count up by 2
        # relative to the non-theme fixed entries + bundles.
        theme_entry_count = sum(
            1 for e in palette._all_entries if e.kind in {"theme_next", "theme_select"}
        )
        assert theme_entry_count == 2, "Expected exactly 2 theme entries"
        assert len(items) == len(palette._all_entries), (
            f"ListView item count ({len(items)}) should match _all_entries "
            f"({len(palette._all_entries)})"
        )


# ---------------------------------------------------------------------------
# _apply_theme helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_theme_changes_app_theme_and_config(tmp_path: object) -> None:
    """_apply_theme sets app.theme and persists to config.display.theme."""
    config = _make_config(theme="textual-dark")

    class _SimpleApp(App):  # type: ignore[type-arg]
        def compose(self) -> ComposeResult:
            return iter([])

    app = _SimpleApp()

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.theme == "textual-dark"

        _apply_theme(app, config, "nord")
        await pilot.pause()

        assert app.theme == "nord"
        assert config.display.theme == "nord"


@pytest.mark.asyncio
async def test_apply_theme_ignores_unknown_name() -> None:
    """_apply_theme does nothing if the theme name is not in available_themes."""
    config = _make_config(theme="textual-dark")

    class _SimpleApp(App):  # type: ignore[type-arg]
        def compose(self) -> ComposeResult:
            return iter([])

    app = _SimpleApp()

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        _apply_theme(app, config, "does-not-exist")
        await pilot.pause()

        # Theme unchanged.
        assert app.theme == "textual-dark"
        assert config.display.theme == "textual-dark"


# ---------------------------------------------------------------------------
# _apply_next_theme helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_next_theme_cycles_forward() -> None:
    """_apply_next_theme advances to the next theme in sorted order."""

    class _SimpleApp(App):  # type: ignore[type-arg]
        def compose(self) -> ComposeResult:
            return iter([])

    app = _SimpleApp()

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        sorted_names = sorted(app.available_themes.keys())
        first_theme = sorted_names[0]
        config = _make_config(theme=first_theme)
        app.theme = first_theme

        _apply_next_theme(app, config)
        await pilot.pause()

        expected_next = sorted_names[1]
        assert app.theme == expected_next
        assert config.display.theme == expected_next


@pytest.mark.asyncio
async def test_apply_next_theme_wraps_around() -> None:
    """_apply_next_theme wraps to the first theme after the last one."""

    class _SimpleApp(App):  # type: ignore[type-arg]
        def compose(self) -> ComposeResult:
            return iter([])

    app = _SimpleApp()

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        sorted_names = sorted(app.available_themes.keys())
        last_theme = sorted_names[-1]
        config = _make_config(theme=last_theme)
        app.theme = last_theme

        _apply_next_theme(app, config)
        await pilot.pause()

        first_theme = sorted_names[0]
        assert app.theme == first_theme
        assert config.display.theme == first_theme


# ---------------------------------------------------------------------------
# ThemeSelector modal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_theme_selector_lists_all_themes() -> None:
    """ThemeSelector ListView contains one item per available theme."""
    from textual.widgets import ListItem

    config = _make_config(theme="textual-dark")
    app = _SelectorApp(config)

    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        selector = app.screen
        assert isinstance(selector, ThemeSelector)

        lv = selector.query_one("#theme-list")
        items = list(lv.query(ListItem))
        # One entry per theme name in selector._theme_names.
        assert len(items) == len(selector._theme_names)
        assert len(items) == len(app.available_themes)


@pytest.mark.asyncio
async def test_theme_selector_current_theme_at_top() -> None:
    """The current theme always appears first in ThemeSelector._theme_names."""
    config = _make_config(theme="nord")
    app = _SelectorApp(config)

    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        selector = app.screen
        assert isinstance(selector, ThemeSelector)

        assert selector._theme_names[0] == "nord"


@pytest.mark.asyncio
async def test_theme_selector_escape_cancels() -> None:
    """Pressing Escape from ThemeSelector returns without changing theme."""
    config = _make_config(theme="textual-dark")
    dismissed_value: list[str | None] = []

    class _SelectorAppCapture(App):  # type: ignore[type-arg]
        def compose(self) -> ComposeResult:
            return iter([])

        def on_mount(self) -> None:
            async def _capture(result: str | None) -> None:
                dismissed_value.append(result)

            self.push_screen(ThemeSelector(config), _capture)

    app = _SelectorAppCapture()

    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert dismissed_value == [None], f"Expected [None], got {dismissed_value}"
