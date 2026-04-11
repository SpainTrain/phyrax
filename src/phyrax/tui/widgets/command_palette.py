"""CommandPalette — fuzzy-search overlay (ctrl+p).

Entries: all bundle names, [Outbox], All Mail, Starred, Sent.
No 'Settings' entry — config is AI-owned via ChatScreen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView

from phyrax.bundler import sort_bundles
from phyrax.config import Bundle, PhyraxConfig


@dataclass
class _PaletteEntry:
    name: str
    kind: str  # "bundle", "outbox", "query"
    bundle: Bundle | None = field(default=None)
    query: str | None = field(default=None)


class CommandPalette(ModalScreen[None]):
    """Fuzzy-search command palette opened by ctrl+p.

    Displays bundle entries (sorted by priority), fixed navigation destinations
    ([Outbox], All Mail, Starred, Sent), and filters them as the user types.
    Pressing Enter activates the highlighted entry; Escape closes without action.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS_PATH = "command_palette.tcss"

    def __init__(self, config: PhyraxConfig) -> None:
        super().__init__()
        self._config = config
        bundles = sort_bundles(config)
        self._all_entries: list[_PaletteEntry] = [
            *[_PaletteEntry(name=b.name, kind="bundle", bundle=b) for b in bundles],
            _PaletteEntry(name="[Outbox]", kind="outbox"),
            _PaletteEntry(name="All Mail", kind="query", query="*"),
            _PaletteEntry(name="Starred", kind="query", query="tag:flagged"),
            _PaletteEntry(name="Sent", kind="query", query="tag:sent"),
        ]
        self._filtered: list[_PaletteEntry] = list(self._all_entries)

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-panel"):
            yield Input(placeholder="Search\u2026", id="search-input")
            yield ListView(id="entry-list")

    def on_mount(self) -> None:
        self._refresh_list()
        self.query_one("#search-input", Input).focus()

    def _refresh_list(self) -> None:
        lv = self.query_one("#entry-list", ListView)
        lv.clear()
        for entry in self._filtered:
            lv.append(ListItem(Label(entry.name)))

    def on_input_changed(self, event: Input.Changed) -> None:
        term = event.value.lower()
        self._filtered = [e for e in self._all_entries if term in e.name.lower()]
        self._refresh_list()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        idx = event.list_view.index
        if idx is None or idx >= len(self._filtered):
            return
        entry = self._filtered[idx]
        self._activate(entry)

    def _activate(self, entry: _PaletteEntry) -> None:
        self.dismiss(None)
        app = self.app
        if entry.kind == "bundle" and entry.bundle is not None:
            # BundleFocusScreen requires a Database reference that lives on the
            # app object. Full wiring happens in E4-3; notify for now.
            app.notify(f"Opening bundle: {entry.bundle.name}")
        elif entry.kind == "outbox":
            app.notify("Outbox not yet implemented (E7-4)")
        else:
            app.notify(f"Query view not yet implemented: {entry.query}")

    def action_cancel(self) -> None:
        """Close the palette without taking any action."""
        self.dismiss(None)
