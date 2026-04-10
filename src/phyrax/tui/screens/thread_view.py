"""ThreadViewScreen — single-thread message reader.

Displays all messages chronologically. HTML-only messages are converted via
html2text for display. Reply (r) is always anchored to the newest message.
ctrl+g opens the thread in Gmail web UI.
"""

from __future__ import annotations

import logging
import subprocess
import uuid
from datetime import UTC, datetime
from typing import ClassVar

import html2text as html2text_lib
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from phyrax.config import DRAFTS_DIR, PhyraxConfig
from phyrax.database import Database
from phyrax.models import AttachmentMeta, Draft, MessageDetail, ThreadSummary
from phyrax.tui.widgets.status_bar import StatusBar

log = logging.getLogger("phyrax")

_DIVIDER = "\u2500" * 60  # ────────────────────────────────────────────────────────────


def _format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_date(timestamp: int) -> str:
    """Format a Unix timestamp as a short human-readable date string."""
    dt = datetime.fromtimestamp(timestamp, tz=UTC)
    return dt.strftime("%a %b %d %Y %H:%M")


def _body_text(msg: MessageDetail) -> str:
    """Return the display body for a message.

    Uses body_plain when non-empty; falls back to html2text conversion of
    body_html. Returns an empty string when neither is available.
    """
    if msg.body_plain:
        return msg.body_plain

    if msg.body_html:
        converter = html2text_lib.HTML2Text()
        converter.ignore_links = False
        converter.body_width = 0  # don't wrap; let the TUI scroll widget handle it
        return converter.handle(msg.body_html)

    return ""


def _render_attachments(attachments: list[AttachmentMeta]) -> str:
    """Render attachment metadata lines."""
    if not attachments:
        return ""
    lines = ["\nAttachments:"]
    for att in attachments:
        size_str = _format_size(att.size_bytes)
        lines.append(f"  {att.filename} \u00b7 {att.content_type} \u00b7 {size_str}")
    return "\n".join(lines)


def _build_message_text(msg: MessageDetail, thread_subject: str) -> str:
    """Compose the full display text block for a single message."""
    parts: list[str] = []

    parts.append(f"From: {msg.from_}")
    if msg.to:
        parts.append(f"To: {', '.join(msg.to)}")
    if msg.cc:
        parts.append(f"Cc: {', '.join(msg.cc)}")
    parts.append(f"Date: {_format_date(msg.date)}")

    # Only show subject when it differs from the thread subject
    if msg.subject and msg.subject != thread_subject:
        parts.append(f"Subject: {msg.subject}")

    parts.append("")  # blank line before body
    parts.append(_body_text(msg))

    attachment_block = _render_attachments(msg.attachments)
    if attachment_block:
        parts.append(attachment_block)

    parts.append("")  # blank line before divider
    parts.append(_DIVIDER)
    return "\n".join(parts)


class ThreadViewScreen(Screen):  # type: ignore[type-arg]  # Textual Screen is generic at runtime
    """Screen that renders every message in a thread chronologically."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "pop_screen", "Back"),
        Binding("r", "reply", "Reply"),
        Binding("ctrl+g", "open_gmail", "Open in Gmail"),
    ]

    def __init__(self, db: Database, thread: ThreadSummary, config: PhyraxConfig) -> None:
        super().__init__()
        self._db = db
        self._thread = thread
        self._config = config
        self._messages: list[MessageDetail] = []

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="message-container")
        yield StatusBar(screen_name="thread")

    def on_mount(self) -> None:
        """Load messages from the database and render them."""
        self._messages = self._db.get_thread_messages(self._thread.thread_id)
        self._render_messages()

    def _render_messages(self) -> None:
        """Mount one Static widget per message into the scroll container."""
        container = self.query_one("#message-container", VerticalScroll)
        container.remove_children()
        for msg in self._messages:
            text = _build_message_text(msg, self._thread.subject)
            container.mount(Static(text, classes="message-block"))

    async def action_reply(self) -> None:
        """Open ComposeModal for the newest message, then save and edit the draft."""
        if not self._messages:
            return
        newest = self._messages[-1]

        # 1. Push ComposeModal and wait for result.
        from phyrax.tui.screens.compose import ComposeIntent, ComposeModal

        intent: ComposeIntent | None = await self.app.push_screen_wait(
            ComposeModal(newest, self._config)
        )
        if intent is None:
            return  # user cancelled

        # 2. Generate or create an empty draft.
        from phyrax.composer import generate_draft, open_editor, save_draft

        if intent.instructions:
            try:
                with self.app.suspend():
                    draft = generate_draft(
                        newest,
                        intent.instructions,
                        self._config,
                        require_full_context=intent.require_full_context,
                    )
            except Exception as exc:
                log.error("action_reply: generate_draft failed: %s", exc)
                self.notify(f"Agent error: {exc}", severity="error")
                return
        else:
            draft_id = str(uuid.uuid4())
            draft = Draft(
                uuid=draft_id,
                thread_id=self._thread.thread_id,
                in_reply_to=newest.message_id,
                to=[newest.from_],
                cc=newest.cc,
                subject=f"Re: {newest.subject}",
                from_=intent.from_alias,
                body_markdown="",
                cache_path=DRAFTS_DIR / f"{draft_id}.txt",
            )

        # 3. Save draft before opening editor (crash recovery).
        save_draft(draft, self._config)

        # 4. Open $EDITOR so the user can review/edit.
        with self.app.suspend():
            draft = open_editor(draft)

        # 5. Re-save after editing and notify.
        save_draft(draft, self._config)
        self.notify("Draft saved. Press o for Outbox.")

    def action_open_gmail(self) -> None:
        """Open the thread in Gmail's web UI via xdg-open."""
        gmail_id = self._thread.gmail_thread_id
        if not gmail_id:
            self.notify("No Gmail thread ID available")
            return
        url = f"https://mail.google.com/mail/u/0/#inbox/{gmail_id}"
        subprocess.run(["xdg-open", url], check=False)
