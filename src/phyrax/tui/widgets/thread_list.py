"""ThreadListWidget — virtualized, reactive thread + bundle header list.

Rows are either bundle headers (selectable, show count/unread) or thread rows
(sender as 'Name (domain.tld)', subject, relative date, unread indicator, tags).
Single shared cursor; j/k stop at boundaries. Rolling viewport queries the DB.
"""

from __future__ import annotations

import email.utils
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView

from phyrax.bundler import sort_bundles
from phyrax.config import Bundle, PhyraxConfig
from phyrax.database import Database
from phyrax.models import ThreadSummary

log = logging.getLogger("phyrax")

# ---------------------------------------------------------------------------
# Row data types
# ---------------------------------------------------------------------------

_MAX_LOAD = 200  # simple full-load cap; rolling viewport is a TODO


@dataclass
class ThreadRow:
    """A single thread entry in the list."""

    thread: ThreadSummary
    bundle_label: str | None  # which bundle this thread belongs to, or None


@dataclass
class BundleHeaderRow:
    """A collapsible bundle section header."""

    bundle: Bundle
    total: int
    unread: int


# Union alias used throughout this module
ListRow = ThreadRow | BundleHeaderRow

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_sender(from_: str) -> str:
    """Format 'Alice <alice@example.com>' as 'Alice (example.com)'.

    Falls back to the bare address when no display name is present, or to the
    raw string when parsing fails entirely.
    """
    name, addr = email.utils.parseaddr(from_)
    if not addr:
        return from_ or "(unknown)"
    domain = addr.split("@")[-1] if "@" in addr else addr
    if name:
        return f"{name} ({domain})"
    return addr


def _format_date(timestamp: int) -> str:
    """Format a Unix timestamp as a compact, human-readable relative string."""
    try:
        dt = datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return ""
    now = datetime.now(tz=UTC)
    delta = now - dt
    if delta.days == 0:
        return dt.strftime("%H:%M")
    if delta.days < 7:
        return dt.strftime("%a")
    if delta.days < 365:
        return dt.strftime("%b %d")
    return dt.strftime("%Y")


def _unread_indicator(tags: frozenset[str]) -> str:
    return "●" if "unread" in tags else "○"


def _tag_pills(tags: frozenset[str]) -> str:
    """Return a compact tag string, excluding system tags."""
    _system = {"inbox", "unread", "attachment", "replied", "passed", "flagged", "draft"}
    pills = sorted(t for t in tags if t not in _system)
    return " ".join(f"[{p}]" for p in pills)


# ---------------------------------------------------------------------------
# Custom ListItem subclasses
# ---------------------------------------------------------------------------


class ThreadRowItem(ListItem):
    """A ListItem that renders a single ThreadSummary row."""

    def __init__(self, row: ThreadRow) -> None:
        super().__init__()
        self._row = row

    def compose(self) -> ComposeResult:
        t = self._row.thread
        sender = _format_sender(t.authors[0]) if t.authors else "(no sender)"
        date = _format_date(t.newest_date)
        unread = _unread_indicator(t.tags)
        pills = _tag_pills(t.tags)

        subject_max = 60
        subject = t.subject[:subject_max] + "…" if len(t.subject) > subject_max else t.subject

        parts = [f"{unread} {sender:<30}  {subject:<{subject_max}}  {date:>8}"]
        if pills:
            parts.append(f"  {pills}")
        yield Label("".join(parts))


class BundleHeaderItem(ListItem):
    """A ListItem that renders a bundle section header."""

    def __init__(self, row: BundleHeaderRow) -> None:
        super().__init__()
        self._row = row

    def compose(self) -> ComposeResult:
        b = self._row.bundle
        label = f"[{b.name} ({self._row.total} · {self._row.unread} unread)] ▶"
        yield Label(label)


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------


class ThreadListWidget(Widget):
    """Virtualized inbox list with bundle headers and shared j/k cursor.

    Loads up to _MAX_LOAD threads per section (rolling viewport is a TODO).
    Emits :class:`ThreadSelected` when the user opens a thread row.
    Emits :class:`BundleHeaderSelected` when a bundle header is activated.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("enter", "select", "Open", show=False),
    ]

    CSS_PATH = "thread_list.tcss"

    # Reactive cursor index — drives highlight refresh.
    cursor: reactive[int] = reactive(0, repaint=True)

    # ---------------------------------------------------------------------------
    # Messages
    # ---------------------------------------------------------------------------

    class ThreadSelected(Message):
        """Posted when the user opens a thread row."""

        def __init__(self, thread: ThreadSummary) -> None:
            super().__init__()
            self.thread = thread

    class BundleHeaderSelected(Message):
        """Posted when the user activates a bundle header row."""

        def __init__(self, bundle: Bundle) -> None:
            super().__init__()
            self.bundle = bundle

    # ---------------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------------

    def __init__(self, db: Database, config: PhyraxConfig) -> None:
        super().__init__()
        self._db = db
        self._config = config
        self._rows: list[ListRow] = []

    async def on_mount(self) -> None:
        self._load_rows()
        await self._rebuild_list()

    # ---------------------------------------------------------------------------
    # Row construction
    # ---------------------------------------------------------------------------

    def _build_unbundled_query(self, bundles: list[Bundle]) -> str:
        """Return the notmuch query for threads not matched by any bundle."""
        if not bundles:
            return "tag:inbox"
        exclusions = " OR ".join(f"tag:{b.label}" for b in bundles)
        return f"tag:inbox AND NOT ({exclusions})"

    def _load_rows(self) -> None:
        """Populate self._rows: unbundled first, then each bundle section."""
        rows: list[ListRow] = []
        sorted_bundles = sort_bundles(self._config)

        # 1. Unbundled threads (inbox but not belonging to any bundle label).
        unbundled_query = self._build_unbundled_query(sorted_bundles)
        try:
            unbundled = self._db.query_threads(unbundled_query, limit=_MAX_LOAD)
        except Exception as exc:
            log.warning("ThreadListWidget: unbundled query failed: %s", exc)
            unbundled = []

        for t in unbundled:
            rows.append(ThreadRow(thread=t, bundle_label=None))

        # 2. Bundle sections in priority order.
        for bundle in sorted_bundles:
            bundle_query = f"tag:inbox AND tag:{bundle.label}"
            try:
                threads = self._db.query_threads(bundle_query, limit=_MAX_LOAD)
                total = self._db.count_threads(bundle_query)
            except Exception as exc:
                log.warning(
                    "ThreadListWidget: bundle query failed for %r: %s",
                    bundle.label,
                    exc,
                )
                threads = []
                total = 0

            unread = sum(1 for t in threads if "unread" in t.tags)
            rows.append(BundleHeaderRow(bundle=bundle, total=total, unread=unread))
            for t in threads:
                rows.append(ThreadRow(thread=t, bundle_label=bundle.label))

        self._rows = rows

    # ---------------------------------------------------------------------------
    # Composition
    # ---------------------------------------------------------------------------

    def _make_list_item(self, row: ListRow) -> ListItem:
        if isinstance(row, BundleHeaderRow):
            return BundleHeaderItem(row)
        return ThreadRowItem(row)

    async def _rebuild_list(self) -> None:
        """Replace ListView contents with the current _rows.

        DOM mutations (clear/append) are awaited so that lv.index is set only
        after all ListItems are mounted and validate_index has non-empty nodes
        to clamp against. Without this, lv.index collapses to None because
        _nodes is empty at validation time, which causes ListView.highlighted_child
        to return None and silently swallow Enter key presses.
        """
        try:
            lv = self.query_one(ListView)
        except Exception:
            return
        await lv.clear()
        for row in self._rows:
            await lv.append(self._make_list_item(row))
        # Sync ListView's internal cursor to ours — nodes are now mounted.
        if self._rows:
            lv.index = min(self.cursor, len(self._rows) - 1)

    def compose(self) -> ComposeResult:
        items = [self._make_list_item(row) for row in self._rows]
        yield ListView(*items, id="thread-listview")

    # ---------------------------------------------------------------------------
    # Cursor actions
    # ---------------------------------------------------------------------------

    def action_cursor_down(self) -> None:
        """Move cursor down one row, stopping at the last row."""
        if self.cursor < len(self._rows) - 1:
            self.cursor += 1
            self._sync_listview_cursor()

    def action_cursor_up(self) -> None:
        """Move cursor up one row, stopping at the first row."""
        if self.cursor > 0:
            self.cursor -= 1
            self._sync_listview_cursor()

    def action_select(self) -> None:
        """Activate the currently highlighted row."""
        if not self._rows:
            return
        idx = min(self.cursor, len(self._rows) - 1)
        row = self._rows[idx]
        if isinstance(row, ThreadRow):
            self.post_message(self.ThreadSelected(row.thread))
        elif isinstance(row, BundleHeaderRow):
            self.post_message(self.BundleHeaderSelected(row.bundle))

    def _sync_listview_cursor(self) -> None:
        """Push cursor position to the inner ListView and scroll into view."""
        try:
            lv = self.query_one(ListView)
        except Exception:
            return
        target = min(self.cursor, len(self._rows) - 1)
        lv.index = target
        # Scroll the highlighted item into view.
        try:
            item = lv.query(ListItem)[target]
            item.scroll_visible()
        except Exception:
            pass

    # ---------------------------------------------------------------------------
    # ListView event passthrough
    # ---------------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle clicks / Enter events bubbled up from the inner ListView."""
        event.stop()
        # Determine which row index was selected.
        try:
            lv = self.query_one(ListView)
            idx = lv.index
        except Exception:
            return
        if idx is None or idx < 0 or idx >= len(self._rows):
            return
        self.cursor = idx
        row = self._rows[idx]
        if isinstance(row, ThreadRow):
            self.post_message(self.ThreadSelected(row.thread))
        elif isinstance(row, BundleHeaderRow):
            self.post_message(self.BundleHeaderSelected(row.bundle))

    # ---------------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------------

    async def reload(self) -> None:
        """Re-query the database and refresh the displayed rows."""
        self._load_rows()
        await self._rebuild_list()
        # Clamp cursor in case rows shrank.
        if self._rows:
            self.cursor = min(self.cursor, len(self._rows) - 1)
        else:
            self.cursor = 0
