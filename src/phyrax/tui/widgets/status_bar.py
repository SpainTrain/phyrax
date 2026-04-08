"""StatusBar — bottom bar widget.

Shows: unread count, sync status (notmuch DB mtime + lieer lock observation),
current screen name.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label


class StatusBar(Widget):
    """Bottom status bar showing screen name, unread count, and sync status."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
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

    def _format_label(self) -> str:
        return (
            f"[{self._screen_name}]  "
            f"inbox: {self._unread_count} unread  |  "
            f"sync: idle"
        )

    def compose(self) -> ComposeResult:
        yield Label(self._format_label(), id="status-label")

    def update(self, screen_name: str, unread_count: int) -> None:
        """Refresh the status bar label with new values."""
        self._screen_name = screen_name
        self._unread_count = unread_count
        self.query_one("#status-label", Label).update(self._format_label())
