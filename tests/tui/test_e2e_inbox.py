"""End-to-end tests for InboxScreen — behavioral and snapshot.

Uses:
- pytest-textual-snapshot (snap_compare) for visual regression snapshots.
- Textual pilot (app.run_test) for behavioral assertions.

Run snapshots:
    uv run pytest tests/tui/test_e2e_inbox.py --snapshot-update   # create / refresh
    uv run pytest tests/tui/test_e2e_inbox.py                     # compare

All tests run against the synthetic fixture mailbox — never the real mailbox.
"""

from __future__ import annotations

import pytest
from textual.app import App

from phyrax.config import PhyraxConfig
from phyrax.database import Database
from phyrax.tui.screens.inbox import InboxScreen
from phyrax.tui.widgets.thread_list import ThreadListWidget, ThreadRow
from tests.fixtures.maildir_builder import MaildirFixture

# ---------------------------------------------------------------------------
# Test app + helpers
# ---------------------------------------------------------------------------


def _make_db(fixture: MaildirFixture) -> Database:
    return Database(path=str(fixture.maildir))


def _make_config() -> PhyraxConfig:
    return PhyraxConfig.model_validate(
        {
            "identity": {"primary": "test@example.com", "aliases": []},
            "ai": {"agent_command": "echo"},
            "bundles": [
                {
                    "name": "Alerts",
                    "label": "alerts",
                    "priority": 1,
                    "rules": [{"field": "from", "operator": "contains", "value": "alerts@"}],
                },
                {
                    "name": "Newsletters",
                    "label": "newsletters",
                    "priority": 2,
                    "rules": [{"field": "from", "operator": "contains", "value": "substack.com"}],
                },
            ],
            "compose": {"include_quote": True},
        }
    )


class _InboxApp(App):  # type: ignore[type-arg]
    """Minimal host App that mounts InboxScreen directly (skips FTUX)."""

    def __init__(self, db: Database, config: PhyraxConfig) -> None:
        super().__init__()
        self._db = db
        self._config = config

    def on_mount(self) -> None:
        self.push_screen(InboxScreen(self._db, self._config))


# ---------------------------------------------------------------------------
# Snapshot test (synchronous — snap_compare runs the app internally)
# ---------------------------------------------------------------------------


def test_inbox_snapshot(snap_compare: object, tmp_maildir: MaildirFixture) -> None:
    """InboxScreen renders the fixture thread list without visual regression."""
    db = _make_db(tmp_maildir)
    config = _make_config()
    app = _InboxApp(db, config)
    assert snap_compare(app, terminal_size=(120, 40))  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Behavioral tests (async — use run_test + pilot)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inbox_thread_list_populated(tmp_maildir: MaildirFixture) -> None:
    """ThreadListWidget is populated after mount."""
    db = _make_db(tmp_maildir)
    config = _make_config()
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        widget = app.screen.query_one(ThreadListWidget)
        assert widget._rows, "ThreadListWidget should have rows after mount"


@pytest.mark.asyncio
async def test_inbox_cursor_moves_with_j_k(tmp_maildir: MaildirFixture) -> None:
    """Pressing j moves cursor down; pressing k moves it back up."""
    db = _make_db(tmp_maildir)
    config = _make_config()
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        widget = app.screen.query_one(ThreadListWidget)
        initial = widget.cursor

        await pilot.press("j")
        await pilot.pause()
        assert widget.cursor == initial + 1, "j should advance cursor"

        await pilot.press("k")
        await pilot.pause()
        assert widget.cursor == initial, "k should retreat cursor"


@pytest.mark.asyncio
async def test_inbox_enter_pushes_thread_view(tmp_maildir: MaildirFixture) -> None:
    """Pressing Enter on a ThreadRow pushes ThreadViewScreen."""
    from phyrax.tui.screens.thread_view import ThreadViewScreen

    db = _make_db(tmp_maildir)
    config = _make_config()
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        widget = app.screen.query_one(ThreadListWidget)

        # Navigate past any bundle headers to land on a ThreadRow
        for _ in range(len(widget._rows)):
            if isinstance(widget._rows[widget.cursor], ThreadRow):
                break
            await pilot.press("j")
            await pilot.pause()

        await pilot.press("enter")
        await pilot.pause(0.3)

        assert isinstance(app.screen, ThreadViewScreen), (
            f"Expected ThreadViewScreen, got {type(app.screen).__name__}"
        )
