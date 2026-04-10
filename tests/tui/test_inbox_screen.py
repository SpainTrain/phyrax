"""TUI shell tests for PhyraxApp and InboxScreen.

Covers:
- App launches without error against the fixture maildir
- Inbox shows expected thread count
- Pressing 'a' on a thread removes it from the visible list
- 'q' exits the app
- PID lockfile created on launch and removed on exit
- Second app instance raises LockfileError while first is running
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from textual.app import App, ComposeResult

import phyrax.config as config_module
from phyrax.config import PhyraxConfig
from phyrax.database import Database
from phyrax.exceptions import LockfileError
from phyrax.tui.screens.inbox import InboxScreen
from phyrax.tui.widgets.thread_list import ThreadListWidget, ThreadRow
from tests.fixtures.maildir_builder import MaildirFixture

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_maildir: MaildirFixture) -> Database:
    """Open a Database pointed at the fixture Maildir."""
    return Database(path=str(tmp_maildir.maildir))


def _make_config() -> PhyraxConfig:
    """Return a minimal PhyraxConfig with no bundles."""
    return PhyraxConfig(bundles=[])


class _InboxApp(App):  # type: ignore[type-arg]
    """Minimal App that mounts InboxScreen — no lockfile, no FTUX routing."""

    def __init__(self, db: Database, config: PhyraxConfig) -> None:
        super().__init__()
        self._db = db
        self._config = config

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(InboxScreen(self._db, self._config))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def patched_lockfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Monkeypatch LOCKFILE to a temp path so tests don't conflict."""
    test_lockfile = tmp_path / "test.lock"
    monkeypatch.setattr(config_module, "LOCKFILE", test_lockfile)
    # Also patch the imported name in app.py
    import phyrax.app as app_module

    monkeypatch.setattr(app_module, "LOCKFILE", test_lockfile)
    return test_lockfile


@pytest.fixture()
def patched_config_load(
    tmp_maildir: MaildirFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Patch PhyraxConfig.load to use the fixture config dir (not real XDG paths)."""
    config_dir = tmp_path / "config" / "phyrax"
    config_dir.mkdir(parents=True)

    minimal_config = {
        "identity": {"primary": "test@example.com", "aliases": []},
        "ai": {"agent_command": "echo"},
        "bundles": [],
        "compose": {"include_quote": True},
    }
    config_path = config_dir / "config.json"
    config_path.write_text(json.dumps(minimal_config, indent=2))

    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))

    # Patch load to always read from fixture config (is_first_run=False)
    original_load = PhyraxConfig.load

    def _patched_load(path: Path = config_path) -> PhyraxConfig:
        return original_load(path=config_path)

    monkeypatch.setattr(PhyraxConfig, "load", staticmethod(_patched_load))
    return config_path


# ---------------------------------------------------------------------------
# Tests: InboxScreen via _InboxApp (no lockfile needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inbox_shows_expected_thread_count(tmp_maildir: MaildirFixture) -> None:
    """The inbox thread list contains all 5 fixture threads (no bundles configured)."""
    db = _make_db(tmp_maildir)
    config = _make_config()
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inbox = app.screen
        assert isinstance(inbox, InboxScreen)

        widget = inbox.query_one(ThreadListWidget)
        thread_rows = [r for r in widget._rows if isinstance(r, ThreadRow)]
        # The fixture has 5 threads: alerts, newsletters, boss, docs, friend.
        assert len(thread_rows) == 5, f"Expected 5 thread rows; got {len(thread_rows)}"

    db.close()


@pytest.mark.asyncio
async def test_archive_removes_thread_from_list(tmp_maildir: MaildirFixture) -> None:
    """Pressing 'a' (action_archive) on the first ThreadRow removes it from the list."""
    db = _make_db(tmp_maildir)
    config = _make_config()
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inbox = app.screen
        assert isinstance(inbox, InboxScreen)

        widget = inbox.query_one(ThreadListWidget)
        # Ensure cursor is on the first ThreadRow
        assert isinstance(widget._rows[0], ThreadRow), "First row should be a ThreadRow"
        count_before = len([r for r in widget._rows if isinstance(r, ThreadRow)])

        # Trigger archive via key press
        await pilot.press("a")
        await pilot.pause()

        count_after = len([r for r in widget._rows if isinstance(r, ThreadRow)])
        assert count_after == count_before - 1, (
            f"Expected {count_before - 1} rows after archive; got {count_after}"
        )

    db.close()


@pytest.mark.asyncio
async def test_q_exits_app(tmp_maildir: MaildirFixture) -> None:
    """Pressing 'q' triggers action_quit and exits the app cleanly."""
    db = _make_db(tmp_maildir)
    config = _make_config()
    app = _InboxApp(db, config)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, InboxScreen)

        await pilot.press("q")
        await pilot.pause()
        # After 'q', the app should have exited; is_running becomes False.
        assert not app.is_running, "App should have stopped after pressing 'q'"


# ---------------------------------------------------------------------------
# Tests: PhyraxApp lockfile behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lockfile_created_on_launch_and_removed_on_exit(
    tmp_maildir: MaildirFixture,
    patched_lockfile: Path,
    patched_config_load: Path,
) -> None:
    """PhyraxApp writes the PID lockfile on mount and deletes it on unmount."""
    from phyrax.app import PhyraxApp

    assert not patched_lockfile.exists(), "Lockfile should not exist before launch"

    async with PhyraxApp().run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert patched_lockfile.exists(), "Lockfile should exist while app is running"
        assert patched_lockfile.read_text().strip().isdigit(), "Lockfile should contain a PID"

    # After the context manager exits, on_unmount has run.
    assert not patched_lockfile.exists(), "Lockfile should be removed after app exits"


@pytest.mark.asyncio
async def test_second_instance_raises_lockfile_error(
    tmp_maildir: MaildirFixture,
    patched_lockfile: Path,
    patched_config_load: Path,
) -> None:
    """A second PhyraxApp raises LockfileError when lockfile already exists."""
    import os

    from phyrax.app import PhyraxApp

    # Pre-create the lockfile with the current PID to simulate a live running instance.
    # Using the current PID ensures os.kill(pid, 0) succeeds and the stale-lockfile
    # cleanup path is NOT triggered, so LockfileError is raised instead.
    patched_lockfile.parent.mkdir(parents=True, exist_ok=True)
    patched_lockfile.write_text(str(os.getpid()), encoding="utf-8")

    with pytest.raises(LockfileError):
        async with PhyraxApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause()
