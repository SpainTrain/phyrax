"""ThemeSelector — modal overlay for browsing and applying built-in themes.

Lists all themes available to the running App, with the current theme
highlighted. Pressing Enter applies and persists the selection; Escape cancels.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView

from phyrax.config import PhyraxConfig


class ThemeSelector(ModalScreen[str | None]):
    """Modal overlay listing all available Textual themes.

    Returns the selected theme name as a string, or ``None`` if the user
    cancelled with Escape.  The caller is responsible for applying the theme
    to ``app.theme`` and persisting it via ``config.save()``.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS_PATH = "theme_selector.tcss"

    def __init__(self, config: PhyraxConfig) -> None:
        super().__init__()
        self._config = config
        self._theme_names: list[str] = []

    def compose(self) -> ComposeResult:
        # Populate theme names from the running app's available_themes dict.
        # Sorted alphabetically for predictable ordering; current theme first.
        current = self._config.display.theme
        all_names = sorted(self.app.available_themes.keys())
        # Reorder so current theme appears at the top.
        ordered = [current] + [n for n in all_names if n != current]
        self._theme_names = ordered

        with Vertical(id="theme-panel"):
            yield Label("Select theme (Escape to cancel)", id="title")
            items = [
                ListItem(Label(f"{name}  (current)" if name == current else name))
                for name in self._theme_names
            ]
            yield ListView(*items, id="theme-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss with the chosen theme name when Enter is pressed."""
        event.stop()
        try:
            lv = self.query_one("#theme-list", ListView)
            idx = lv.index
        except Exception:
            return
        if idx is not None and 0 <= idx < len(self._theme_names):
            self.dismiss(self._theme_names[idx])

    def action_cancel(self) -> None:
        """Dismiss with None when Escape is pressed."""
        self.dismiss(None)
