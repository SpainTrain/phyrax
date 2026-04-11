"""StatusBar — bottom bar widget.

Shows: unread count, sync status (notmuch DB mtime + lieer lock observation),
current screen name.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label


def _get_notmuch_db_path() -> Path | None:
    """Resolve the notmuch database path via notmuch CLI."""
    try:
        result = subprocess.run(
            ["notmuch", "config", "get", "database.path"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, AttributeError):
        return None


def _sync_status(db_path: Path | None) -> str:
    """Return the current sync status string."""
    if db_path is None:
        return "sync: unknown"

    xapian_dir = db_path / ".notmuch" / "xapian"

    if not xapian_dir.exists():
        return "sync: no DB"

    # Check if a write is in progress (flintlock file indicates active write).
    flintlock = xapian_dir / "flintlock"
    if flintlock.exists():
        return "sync: syncing\u2026"

    # Compute time since last sync using xapian dir mtime as proxy.
    mtime = xapian_dir.stat().st_mtime
    elapsed_seconds = time.time() - mtime
    elapsed_minutes = int(elapsed_seconds / 60)

    if elapsed_seconds > 3600:  # > 1 hour
        return "sync: \u26a0 stale"

    if elapsed_minutes < 1:
        return "sync: just now"

    return f"sync: {elapsed_minutes}m ago"


class StatusBar(Widget):
    """Bottom status bar showing screen name, unread count, and sync status."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
    }
    StatusBar Label.sync-stale {
        color: $warning;
    }
    """

    def __init__(
        self,
        screen_name: str = "inbox",
        unread_count: int = 0,
    ) -> None:
        super().__init__()
        self._screen_name = screen_name
        self._unread_count = unread_count
        self._db_path: Path | None = None
        self._sync_text: str = "sync: idle"

    def _format_label(self) -> str:
        return f"[{self._screen_name}]  inbox: {self._unread_count} unread  |  {self._sync_text}"

    def compose(self) -> ComposeResult:
        yield Label(self._format_label(), id="status-label")

    def on_mount(self) -> None:
        """Start polling for sync status every 10 seconds."""
        self.set_interval(10, self._update_sync_status)

    def _update_sync_status(self) -> None:
        """Poll sync state and refresh the label.

        DB path is resolved lazily on the first poll so that the subprocess
        call does not fire during widget mount (avoids interference with
        test mocks that patch subprocess.run).
        """
        if self._db_path is None:
            self._db_path = _get_notmuch_db_path()
        self._sync_text = _sync_status(self._db_path)
        label = self.query_one("#status-label", Label)
        label.update(self._format_label())
        # Toggle warning style class when sync is stale.
        label.set_class("\u26a0" in self._sync_text, "sync-stale")

    def update(self, screen_name: str, unread_count: int) -> None:
        """Refresh the status bar label with new values."""
        self._screen_name = screen_name
        self._unread_count = unread_count
        self.query_one("#status-label", Label).update(self._format_label())
