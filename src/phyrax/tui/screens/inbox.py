"""InboxScreen — the default Phyrax screen.

Shows bundles (priority-sorted, selectable headers) interleaved with unbundled
threads. Bundle headers and thread rows share a single cursor. Cursor stops at
boundaries (no wrap). Keybindings are read from config.keys.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Footer

from phyrax.actions.builtins import run_task_action
from phyrax.bundler import generate_bundle_rule
from phyrax.config import PhyraxConfig
from phyrax.database import Database
from phyrax.tui.widgets.action_menu import run_action_for_thread
from phyrax.tui.widgets.command_palette import CommandPalette
from phyrax.tui.widgets.feedback_modal import FeedbackModal
from phyrax.tui.widgets.status_bar import StatusBar
from phyrax.tui.widgets.thread_list import (
    BundleHeaderRow,
    ThreadListWidget,
    ThreadRow,
)

log = logging.getLogger("phyrax")


class InboxScreen(Screen):  # type: ignore[type-arg]  # Textual Screen is generic at runtime but unparameterized here
    """Main inbox screen — bundles and threads with full keybinding dispatch."""

    # BINDINGS uses the default key strings so that Textual's footer and help
    # system show sensible defaults. Action handlers still look up config.keys
    # at runtime, so user overrides take effect (subject to re-mount).
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("enter", "select", "Open"),
        Binding("a", "archive", "Archive"),
        Binding("r", "reply", "Reply"),
        Binding("t", "task_action", "Task"),
        Binding("space", "action_menu", "Actions"),
        Binding("o", "outbox", "Outbox"),
        Binding("ctrl+p", "command_palette", "Palette"),
        Binding("?", "chat", "Chat"),
        Binding("f", "feedback", "Feedback", show=False),
    ]

    def __init__(self, db: Database, config: PhyraxConfig) -> None:
        super().__init__()
        self._db = db
        self._config = config

    def compose(self) -> ComposeResult:
        yield ThreadListWidget(self._db, self._config)
        yield StatusBar()
        yield Footer()

    # ---------------------------------------------------------------------------
    # Message handlers — ThreadListWidget bubbles these up instead of acting
    # directly so that the Screen owns navigation.
    # ---------------------------------------------------------------------------

    def on_thread_list_widget_thread_selected(self, event: ThreadListWidget.ThreadSelected) -> None:
        """Open ThreadViewScreen for the selected thread."""
        from phyrax.tui.screens.thread_view import ThreadViewScreen

        event.stop()
        self.app.push_screen(ThreadViewScreen(self._db, event.thread, self._config))

    def on_thread_list_widget_bundle_header_selected(
        self, event: ThreadListWidget.BundleHeaderSelected
    ) -> None:
        """Push BundleFocusScreen for the selected bundle."""
        from phyrax.tui.screens.bundle_focus import BundleFocusScreen

        event.stop()
        self.app.push_screen(BundleFocusScreen(self._db, event.bundle, self._config))

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def _get_selected_row(self) -> ThreadRow | BundleHeaderRow | None:
        """Return the currently selected row from ThreadListWidget, or None."""
        try:
            widget = self.query_one(ThreadListWidget)
        except Exception:
            return None
        if not widget._rows:
            return None
        idx = min(widget.cursor, len(widget._rows) - 1)
        return widget._rows[idx]

    # ---------------------------------------------------------------------------
    # Action handlers
    # ---------------------------------------------------------------------------

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    async def action_archive(self) -> None:
        """Archive the selected thread or all threads under a bundle header."""
        row = self._get_selected_row()
        if row is None:
            self.notify("Nothing selected")
            return

        if isinstance(row, ThreadRow):
            try:
                self._db.remove_tags(row.thread.thread_id, ["inbox"])
            except Exception as exc:
                log.error("action_archive: remove_tags failed: %s", exc)
                self.notify(f"Archive failed: {exc}", severity="error")
                return
            try:
                await self.query_one(ThreadListWidget).reload()
            except Exception as exc:
                log.warning("action_archive: reload failed: %s", exc)

        elif isinstance(row, BundleHeaderRow):
            query = f"tag:{row.bundle.label} AND tag:inbox"
            try:
                threads = self._db.query_threads(query, limit=500)
            except Exception as exc:
                log.error("action_archive (bundle): query failed: %s", exc)
                self.notify(f"Archive failed: {exc}", severity="error")
                return
            count = 0
            for t in threads:
                try:
                    self._db.remove_tags(t.thread_id, ["inbox"])
                    count += 1
                except Exception as exc:
                    log.warning(
                        "action_archive (bundle): remove_tags failed for %r: %s",
                        t.thread_id,
                        exc,
                    )
            try:
                await self.query_one(ThreadListWidget).reload()
            except Exception as exc:
                log.warning("action_archive (bundle): reload failed: %s", exc)
            self.notify(f"Archived {count} threads from {row.bundle.name}")

    def action_select(self) -> None:
        """Open the selected thread or bundle (delegates to ThreadListWidget.action_select)."""
        try:
            self.query_one(ThreadListWidget).action_select()
        except Exception as exc:
            log.warning("action_select: %s", exc)

    async def action_feedback(self) -> None:
        """Show FeedbackModal, call AI agent to propose a BundleRule, and log it."""
        row = self._get_selected_row()
        if not isinstance(row, ThreadRow):
            self.notify("Select a thread first")
            return

        # 1. Get user description via modal.
        description: str | None = await self.app.push_screen_wait(FeedbackModal(row.thread.subject))
        if not description:
            return

        # 2. Get the newest message in the thread for context.
        messages = self._db.get_thread_messages(row.thread.thread_id)
        if not messages:
            self.notify("Thread has no messages")
            return
        newest = messages[-1]

        # 3. Run agent (captured mode — no terminal handoff needed).
        try:
            rule = generate_bundle_rule(newest, description, self._config)
        except Exception as exc:
            log.error("action_feedback: generate_bundle_rule failed: %s", exc)
            self.notify(f"Agent error: {exc}", severity="error")
            return

        # 4. Notify the user of the proposed rule.
        # Full confirmation and config-write flow is wired in E3-4.
        value_display = rule.value if rule.value is not None else "(exists)"
        log.info(
            "action_feedback: proposed rule: field=%r operator=%r value=%r",
            rule.field,
            rule.operator,
            rule.value,
        )
        self.notify(
            f"Proposed rule: {rule.field} {rule.operator} {value_display}"
            " \u2014 add it? (y/n not wired)"
        )

    def action_task_action(self) -> None:
        """Run the task action for the currently selected thread."""
        row = self._get_selected_row()
        if not isinstance(row, ThreadRow):
            self.notify("Select a thread first")
            return
        with self.app.suspend():
            ran = run_task_action(self._db, row.thread, self._config)
        if not ran:
            self.notify("No task action configured — ask the chat agent to set one up")
            return
        self.notify("Task action ran. Tag +task-created? (y/n) — not yet wired")

    async def action_action_menu(self) -> None:
        """Open the ActionMenu overlay for the currently selected thread."""
        row = self._get_selected_row()
        if not isinstance(row, ThreadRow):
            self.notify("Select a thread first")
            return
        messages = self._db.get_thread_messages(row.thread.thread_id)
        if not messages:
            self.notify("Thread has no messages")
            return
        await run_action_for_thread(self.app, messages[-1], self._config)

    def action_outbox(self) -> None:
        """Push OutboxScreen for draft review and dispatch."""
        from phyrax.tui.screens.outbox import OutboxScreen

        self.app.push_screen(OutboxScreen())

    def action_command_palette(self) -> None:
        """Open the command palette overlay."""
        self.app.push_screen(CommandPalette(self._config))

    def action_chat(self) -> None:
        """Push ChatScreen for the AI mailbox assistant."""
        try:
            from phyrax.tui.screens.chat import ChatScreen

            self.app.push_screen(ChatScreen())
        except Exception as exc:
            log.warning("action_chat: failed to push ChatScreen: %s", exc)
            self.notify("Chat not yet implemented (E9-1)")
