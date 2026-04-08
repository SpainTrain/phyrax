"""InboxScreen — the default Phyrax screen.

Shows bundles (priority-sorted, selectable headers) interleaved with unbundled
threads. Bundle headers and thread rows share a single cursor. Cursor stops at
boundaries (no wrap). Keybindings are read from config.keys.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Label

from phyrax.tui.widgets.status_bar import StatusBar


class InboxScreen(Screen):  # type: ignore[type-arg]  # Textual Screen is generic at runtime but unparameterized here
    """Main inbox screen — placeholder shell for E4-2 virtualized thread list."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Label("Loading threads…")
        yield StatusBar()

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()
