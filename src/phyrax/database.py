"""notmuch query abstraction layer.

This is the SOLE module that imports notmuch2. All other modules depend on the
dataclasses returned here (ThreadSummary, MessageDetail) — never on notmuch2
types directly.
"""

from __future__ import annotations

from phyrax.models import MessageDetail, ThreadSummary


class Database:
    """Thin wrapper around the notmuch2 Python bindings."""

    def __init__(self, path: str | None = None) -> None:
        """Open the notmuch database.

        Args:
            path: Explicit DB path. If None, discovered via
                  ``notmuch config get database.path``.
        """
        raise NotImplementedError

    def query_threads(
        self,
        query: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ThreadSummary]:
        """Run a notmuch query and return a window of thread summaries."""
        raise NotImplementedError

    def count_threads(self, query: str) -> int:
        """Return the total thread count for a query (fast Xapian count)."""
        raise NotImplementedError

    def get_thread_messages(self, thread_id: str) -> list[MessageDetail]:
        """Return all messages in a thread, ordered chronologically."""
        raise NotImplementedError

    def add_tags(self, thread_id: str, tags: list[str]) -> None:
        """Add tags to every message in a thread."""
        raise NotImplementedError

    def remove_tags(self, thread_id: str, tags: list[str]) -> None:
        """Remove tags from every message in a thread."""
        raise NotImplementedError

    def get_attachment_content(self, message_id: str, filename: str) -> bytes:
        """Extract attachment bytes from the MIME tree of a message."""
        raise NotImplementedError

    def close(self) -> None:
        """Close the notmuch database handle."""
        raise NotImplementedError

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
