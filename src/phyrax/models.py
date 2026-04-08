"""Domain dataclasses: ThreadSummary, MessageDetail, AttachmentMeta, Draft.

These are the canonical data transfer objects produced by database.py and
consumed by every other module. No notmuch2 types leak beyond this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AttachmentMeta:
    """Metadata for a MIME attachment (content not loaded)."""

    filename: str
    content_type: str
    size_bytes: int


@dataclass
class ThreadSummary:
    """Lightweight representation of a notmuch thread, used in list views."""

    thread_id: str
    subject: str
    authors: list[str]
    newest_date: int  # Unix timestamp
    message_count: int
    tags: frozenset[str]
    snippet: str  # First 200 chars of newest message body, quotes stripped
    gmail_thread_id: str  # From X-GM-THRID header


@dataclass
class MessageDetail:
    """Full message representation with headers, body, and attachment metadata."""

    message_id: str
    thread_id: str
    from_: str
    to: list[str]
    cc: list[str]
    date: int  # Unix timestamp
    subject: str
    headers: dict[str, str]  # All headers, keyed by name
    body_plain: str  # text/plain part, or empty string
    body_html: str | None  # text/html part if present
    tags: frozenset[str]
    attachments: list[AttachmentMeta] = field(default_factory=list)


@dataclass
class Draft:
    """An unsent reply staged in the drafts cache directory."""

    uuid: str
    thread_id: str
    in_reply_to: str  # Message-ID of the message being replied to
    to: list[str]
    cc: list[str]
    subject: str
    from_: str  # The alias chosen for this reply
    body_markdown: str
    cache_path: Path  # ~/.cache/phyrax/drafts/{uuid}.txt
