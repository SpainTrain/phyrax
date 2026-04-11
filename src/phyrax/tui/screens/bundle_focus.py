"""BundleFocusScreen — filtered thread list for a single bundle.

Reuses ThreadListWidget with query ``tag:{bundle.label} AND tag:inbox``.
All InboxScreen keybindings work within the filtered context.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Label

from phyrax.config import Bundle, PhyraxConfig
from phyrax.database import Database
from phyrax.tui.widgets.status_bar import StatusBar
from phyrax.tui.widgets.thread_list import ThreadListWidget, ThreadRow

log = logging.getLogger("phyrax")


class _BundleThreadListWidget(ThreadListWidget):
    """ThreadListWidget variant that loads only threads for a single bundle.

    Overrides ``_load_rows`` to query by the bundle label, producing a flat
    list of thread rows (no bundle headers).
    """

    def __init__(self, db: Database, config: PhyraxConfig, bundle: Bundle) -> None:
        super().__init__(db, config)
        self._bundle = bundle

    def _load_rows(self) -> None:
        """Load threads matching tag:{bundle.label} AND tag:inbox."""
        query = f"tag:{self._bundle.label} AND tag:inbox"
        try:
            threads = self._db.query_threads(query, limit=200)
        except Exception as exc:
            log.warning(
                "_BundleThreadListWidget: query failed for bundle %r: %s",
                self._bundle.label,
                exc,
            )
            threads = []

        self._rows = [ThreadRow(thread=t, bundle_label=self._bundle.label) for t in threads]


class BundleFocusScreen(Screen):  # type: ignore[type-arg]  # Textual Screen is generic at runtime but unparameterized here
    """Thread list filtered to a single bundle.

    Pushed when the user activates a bundle header in InboxScreen.
    Escape pops back. 'a' archives all threads in the bundle.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("a", "archive_bundle", "Archive bundle", show=False),
    ]

    def __init__(self, db: Database, bundle: Bundle, config: PhyraxConfig) -> None:
        super().__init__()
        self._db = db
        self._bundle = bundle
        self._config = config

    def compose(self) -> ComposeResult:
        yield Label(f"[{self._bundle.name}]", id="bundle-title")
        yield _BundleThreadListWidget(self._db, self._config, self._bundle)
        yield StatusBar(screen_name=self._bundle.name)

    def _key_escape(self) -> None:
        """Pop back to InboxScreen when Escape is pressed.

        Screen._key_escape only calls clear_selection(), which swallows the key
        without triggering the ``escape → app.pop_screen`` binding. Override it
        here to perform the navigation instead.
        """
        self.app.pop_screen()

    async def action_archive_bundle(self) -> None:
        """Archive every thread in this bundle (remove 'inbox' tag from all threads)."""
        query = f"tag:{self._bundle.label} AND tag:inbox"
        try:
            threads = self._db.query_threads(query, limit=500)
        except Exception as exc:
            log.error("BundleFocusScreen: archive query failed: %s", exc)
            self.notify(f"Archive failed: {exc}", severity="error")
            return

        count = 0
        for thread in threads:
            try:
                self._db.remove_tags(thread.thread_id, ["inbox"])
                count += 1
            except Exception as exc:
                log.warning(
                    "BundleFocusScreen: remove_tags failed for thread %r: %s",
                    thread.thread_id,
                    exc,
                )

        try:
            await self.query_one(_BundleThreadListWidget).reload()
        except Exception as exc:
            log.warning("BundleFocusScreen: reload after archive failed: %s", exc)

        self.notify(f"Archived {count} threads from {self._bundle.name}")
