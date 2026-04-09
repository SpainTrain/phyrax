"""PhyraxApp — Textual App subclass and TUI entrypoint.

On mount: acquires PID lockfile, loads config, opens Database. If first run,
routes to FTUX bootstrap + ChatScreen handoff before showing InboxScreen.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Callable
from typing import Any, ClassVar

from textual.app import App, ComposeResult
from textual.screen import Screen

from phyrax.config import LOCKFILE, PhyraxConfig
from phyrax.database import Database
from phyrax.exceptions import LockfileError
from phyrax.ftux.wizard import run_bootstrap_wizard, run_post_bootstrap_handoff
from phyrax.tui.screens.inbox import InboxScreen

log = logging.getLogger("phyrax")


class PhyraxApp(App):  # type: ignore[type-arg]  # Textual App is generic at runtime but unparameterized here
    """Phyrax TUI application."""

    CSS_PATH = None  # styled programmatically
    SCREENS: ClassVar[dict[str, Callable[[], Screen[Any]]]] = {}

    def compose(self) -> ComposeResult:
        # App.compose() must yield something; InboxScreen is pushed in on_mount.
        return iter([])

    def on_mount(self) -> None:
        """Acquire lockfile, load config, open DB, route FTUX or InboxScreen."""
        # 1. Acquire PID lockfile.
        LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
        if LOCKFILE.exists():
            raise LockfileError(
                f"Another phr instance may be running (lockfile exists: {LOCKFILE}). "
                "Remove it manually if the previous instance crashed."
            )
        LOCKFILE.write_text(str(os.getpid()), encoding="utf-8")

        # 2. Load config.
        config = PhyraxConfig.load()

        # 3. Open database.
        self._db = Database()

        # 4. FTUX routing.
        if config.is_first_run:
            ai_config = run_bootstrap_wizard()
            config.ai = ai_config
            config.save()
            with contextlib.suppress(NotImplementedError):
                run_post_bootstrap_handoff(self)

        # 5. Push InboxScreen.
        self.push_screen(InboxScreen(self._db, config))

    def on_unmount(self) -> None:
        """Clean up lockfile and database on exit."""
        try:
            LOCKFILE.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Could not remove lockfile %s: %s", LOCKFILE, exc)

        with contextlib.suppress(AttributeError):
            self._db.close()  # _db may not be set if on_mount failed early

    async def action_quit(self) -> None:
        """Exit the application."""
        self.exit()


def run_app() -> None:
    """Launch the PhyraxApp TUI."""
    PhyraxApp().run()
