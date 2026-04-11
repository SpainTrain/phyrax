"""OutboxScreen — draft staging area and dispatch queue.

Lists ~/.cache/phyrax/drafts/*.txt. Supports: preview (Enter), edit (e),
HTML preview in browser (p), discard (d), send (s).
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import UTC, datetime
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import DataTable, Static

from phyrax.composer import cleanup_draft, recover_unsent_drafts
from phyrax.exceptions import SendError
from phyrax.models import Draft
from phyrax.sender import preview_in_browser, render_html, send_reply
from phyrax.tui.widgets.status_bar import StatusBar

log = logging.getLogger("phyrax")


class OutboxScreen(Screen[None]):
    """Lists, previews, edits, and dispatches draft emails."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "pop_screen", "Back"),
        Binding("e", "edit_draft", "Edit", show=True),
        Binding("p", "preview_draft", "Preview", show=True),
        Binding("d", "discard_draft", "Discard", show=True),
        Binding("s", "send_draft", "Send", show=True),
    ]

    CSS_PATH = "outbox.tcss"

    def compose(self) -> ComposeResult:
        yield DataTable(id="draft-table")
        yield Static(id="preview-pane")
        yield StatusBar(screen_name="outbox")

    def on_mount(self) -> None:
        self._reload()

    def _reload(self) -> None:
        self._drafts: list[Draft] = recover_unsent_drafts()
        table = self.query_one("#draft-table", DataTable)
        table.clear(columns=True)
        table.add_columns("To", "Subject", "Modified")
        for draft in self._drafts:
            mtime = draft.cache_path.stat().st_mtime if draft.cache_path.exists() else 0
            dt = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d %H:%M")
            table.add_row(", ".join(draft.to), draft.subject, dt)
        # Clear preview pane after reload
        self.query_one("#preview-pane", Static).update("")

    def _selected_draft(self) -> Draft | None:
        table = self.query_one("#draft-table", DataTable)
        if table.cursor_row < 0 or table.cursor_row >= len(self._drafts):
            return None
        return self._drafts[table.cursor_row]

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Show preview when Enter is pressed on a row."""
        draft = self._selected_draft()
        if draft is None:
            return
        preview = self.query_one("#preview-pane", Static)
        lines = [
            f"From:    {draft.from_}",
            f"To:      {', '.join(draft.to)}",
            f"Subject: {draft.subject}",
            "",
            draft.body_markdown,
        ]
        preview.update("\n".join(lines))

    def action_edit_draft(self) -> None:
        """Open $EDITOR on the selected draft; re-parse on resume."""
        draft = self._selected_draft()
        if not draft:
            self.notify("No draft selected")
            return
        editor = os.environ.get("EDITOR", "vi")
        with self.app.suspend():
            subprocess.run([editor, str(draft.cache_path)], check=False)
        self._reload()

    def action_preview_draft(self) -> None:
        """Render Markdown body to HTML and open in the default browser."""
        draft = self._selected_draft()
        if not draft:
            self.notify("No draft selected")
            return
        try:
            html = render_html(draft.body_markdown)
            preview_in_browser(html)
        except SendError as exc:
            log.error("preview_draft: render failed: %s", exc)
            self.notify(f"Preview failed: {exc}", severity="error")

    def action_discard_draft(self) -> None:
        """Delete the selected draft from disk (no undo)."""
        draft = self._selected_draft()
        if not draft:
            self.notify("No draft selected")
            return
        cleanup_draft(draft)
        self.notify(f"Draft discarded: {draft.subject}")
        self._reload()

    def action_send_draft(self) -> None:
        """Dispatch the selected draft via gmi send -t."""
        draft = self._selected_draft()
        if not draft:
            self.notify("No draft selected")
            return
        try:
            send_reply(draft)
            self.notify(f"Sent: {draft.subject}")
            self._reload()
        except SendError as exc:
            log.error("send_draft: send failed: %s", exc)
            self.notify(f"Send failed: {exc}", severity="error")
        except OSError as exc:
            # Catch filesystem errors (e.g. draft deleted externally) to keep
            # the draft on disk and surface the error to the user.
            log.error("send_draft: OS error: %s", exc)
            self.notify(f"Send failed: {exc}", severity="error")
