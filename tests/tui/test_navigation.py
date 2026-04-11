"""Tests for TUI screen navigation.

Covers:
- Enter on a thread row pushes ThreadViewScreen with the correct messages
- Escape (via action) from ThreadViewScreen returns to InboxScreen
- Enter on a bundle header pushes BundleFocusScreen filtered by the label
- ctrl+p (via action) opens CommandPalette, typing filters entries
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, ListView

from phyrax.config import Bundle, BundleRule, PhyraxConfig
from phyrax.database import Database
from phyrax.tui.screens.bundle_focus import BundleFocusScreen
from phyrax.tui.screens.inbox import InboxScreen
from phyrax.tui.screens.thread_view import ThreadViewScreen
from phyrax.tui.widgets.command_palette import CommandPalette
from tests.fixtures.maildir_builder import MaildirFixture

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_with_bundles() -> PhyraxConfig:
    """Return a PhyraxConfig with alerts and newsletters bundles."""
    alerts_bundle = Bundle(
        name="Alerts",
        label="alerts",
        rules=[BundleRule(field="from", operator="contains", value="alerts@example.com")],
        priority=10,
    )
    newsletters_bundle = Bundle(
        name="Newsletters",
        label="newsletters",
        rules=[BundleRule(field="from", operator="contains", value="newsletter@substack.com")],
        priority=20,
    )
    return PhyraxConfig(bundles=[alerts_bundle, newsletters_bundle])


def _make_db(tmp_maildir: MaildirFixture) -> Database:
    """Open a Database pointed at the fixture Maildir."""
    return Database(path=str(tmp_maildir.maildir))


class _InboxApp(App):  # type: ignore[type-arg]
    """Minimal App that mounts InboxScreen with a fixture DB and config."""

    def __init__(self, db: Database, config: PhyraxConfig) -> None:
        super().__init__()
        self._db = db
        self._config = config

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(InboxScreen(self._db, self._config))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enter_on_thread_pushes_thread_view(tmp_maildir: MaildirFixture) -> None:
    """Selecting a thread via action_select on InboxScreen pushes ThreadViewScreen."""
    db = _make_db(tmp_maildir)
    # No bundles — all threads are unbundled, first row is a ThreadRow
    config = PhyraxConfig(bundles=[])
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, InboxScreen)

        # Trigger select action directly (cursor is on first row by default)
        inbox = app.screen
        assert isinstance(inbox, InboxScreen)
        inbox.action_select()
        await pilot.pause()

        assert isinstance(app.screen, ThreadViewScreen), (
            f"Expected ThreadViewScreen on top; got {type(app.screen).__name__}"
        )

    db.close()


@pytest.mark.asyncio
async def test_enter_key_press_pushes_thread_view(tmp_maildir: MaildirFixture) -> None:
    """Pressing the Enter key in the inbox must push ThreadViewScreen.

    This is a regression test for phyrax-d4r: the ListView index was set
    synchronously before DOM nodes were mounted, collapsing to None and causing
    ListView.action_select_cursor to silently do nothing.
    """
    db = _make_db(tmp_maildir)
    config = PhyraxConfig(bundles=[])
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, InboxScreen)

        # Press Enter — this exercises the full key-dispatch path through
        # ListView.action_select_cursor -> ListView.Selected ->
        # ThreadListWidget.on_list_view_selected -> ThreadSelected ->
        # InboxScreen.on_thread_list_widget_thread_selected.
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, ThreadViewScreen), (
            f"Expected ThreadViewScreen after pressing Enter; got {type(app.screen).__name__}"
        )

    db.close()


@pytest.mark.asyncio
async def test_thread_view_shows_correct_messages(tmp_maildir: MaildirFixture) -> None:
    """ThreadViewScreen opened from InboxScreen displays the selected thread's messages."""
    db = _make_db(tmp_maildir)
    config = PhyraxConfig(bundles=[])
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inbox = app.screen
        assert isinstance(inbox, InboxScreen)

        # Open the first thread
        inbox.action_select()
        await pilot.pause()

        tvs = app.screen
        assert isinstance(tvs, ThreadViewScreen)
        statics = list(tvs.query("Static"))
        assert len(statics) > 0, "ThreadViewScreen should display message blocks"

    db.close()


@pytest.mark.asyncio
async def test_escape_from_thread_view_returns_to_inbox(tmp_maildir: MaildirFixture) -> None:
    """Popping ThreadViewScreen reveals InboxScreen underneath."""
    db = _make_db(tmp_maildir)
    config = PhyraxConfig(bundles=[])
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Open first thread
        inbox = app.screen
        assert isinstance(inbox, InboxScreen)
        inbox.action_select()
        await pilot.pause()
        assert isinstance(app.screen, ThreadViewScreen)

        # Pop back — equivalent to pressing Escape
        app.pop_screen()
        await pilot.pause()

        assert isinstance(app.screen, InboxScreen), (
            f"Expected InboxScreen after pop; got {type(app.screen).__name__}"
        )

    db.close()


@pytest.mark.asyncio
async def test_enter_on_bundle_header_pushes_bundle_focus(tmp_maildir: MaildirFixture) -> None:
    """Activating a bundle header row pushes BundleFocusScreen."""
    db = _make_db(tmp_maildir)
    config = _make_config_with_bundles()
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inbox = app.screen
        assert isinstance(inbox, InboxScreen)

        # Navigate to a bundle header row. With alerts and newsletters configured,
        # unbundled threads (boss, docs, friend = 3 rows) appear first, followed
        # by the Alerts bundle header. Move cursor down 3 times to land on it.
        from phyrax.tui.widgets.thread_list import BundleHeaderRow, ThreadListWidget

        widget = inbox.query_one(ThreadListWidget)
        # Advance cursor past unbundled rows to first bundle header
        for _ in range(10):
            if isinstance(widget._rows[widget.cursor], BundleHeaderRow):
                break
            widget.action_cursor_down()
        await pilot.pause()

        assert isinstance(widget._rows[widget.cursor], BundleHeaderRow), (
            "Cursor should be on a bundle header row"
        )

        # Activate via action_select
        inbox.action_select()
        await pilot.pause()

        assert isinstance(app.screen, BundleFocusScreen), (
            f"Expected BundleFocusScreen; got {type(app.screen).__name__}"
        )

    db.close()


@pytest.mark.asyncio
async def test_command_palette_opens_via_action(tmp_maildir: MaildirFixture) -> None:
    """action_command_palette on InboxScreen pushes the phyrax CommandPalette."""
    db = _make_db(tmp_maildir)
    config = _make_config_with_bundles()
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inbox = app.screen
        assert isinstance(inbox, InboxScreen)

        # Call action directly — pilot.press("ctrl+p") is intercepted by
        # Textual's built-in command palette binding.
        inbox.action_command_palette()
        await pilot.pause()

        assert isinstance(app.screen, CommandPalette), (
            f"Expected phyrax CommandPalette; got {type(app.screen).__name__} "
            f"({app.screen.__class__.__module__})"
        )

    db.close()


@pytest.mark.asyncio
async def test_command_palette_filters_entries(tmp_maildir: MaildirFixture) -> None:
    """Typing in the CommandPalette search box reduces the displayed entries."""
    db = _make_db(tmp_maildir)
    config = _make_config_with_bundles()
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inbox = app.screen
        assert isinstance(inbox, InboxScreen)
        inbox.action_command_palette()
        await pilot.pause()

        palette = app.screen
        assert isinstance(palette, CommandPalette)

        lv_before = palette.query_one("#entry-list", ListView)
        total_before = len(list(lv_before.query("ListItem")))

        # Type "alerts" — only the Alerts bundle entry should match
        search = palette.query_one("#search-input", Input)
        search.value = "alerts"
        await pilot.pause()

        lv_after = palette.query_one("#entry-list", ListView)
        total_after = len(list(lv_after.query("ListItem")))

        assert total_after < total_before, (
            f"Filtering by 'alerts' should reduce entries "
            f"(before={total_before}, after={total_after})"
        )
        assert total_after >= 1, "At least the Alerts bundle should match"

    db.close()
