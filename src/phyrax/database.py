"""notmuch query abstraction layer.

This is the SOLE module that imports notmuch2. All other modules depend on the
dataclasses returned here (ThreadSummary, MessageDetail) — never on notmuch2
types directly.
"""

from __future__ import annotations

import contextlib
import email
import email.policy
import logging
import subprocess
from email.message import Message
from typing import Any

import notmuch2  # type: ignore[import-untyped]  # CFFI binding; no stub available

from phyrax.exceptions import DatabaseError
from phyrax.models import AttachmentMeta, MessageDetail, ThreadSummary

log = logging.getLogger("phyrax")


def _resolve_db_path() -> str:
    """Return the notmuch database path via ``notmuch config get database.path``."""
    try:
        result = subprocess.run(
            ["notmuch", "config", "get", "database.path"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise DatabaseError(f"Could not determine notmuch database path: {exc}") from exc


def _parse_authors(authors_raw: str) -> list[str]:
    """Split the notmuch authors string into a deduplicated list."""
    seen: set[str] = set()
    result: list[str] = []
    for author in (a.strip() for a in authors_raw.split("|")):
        if author and author not in seen:
            seen.add(author)
            result.append(author)
    return result


def _strip_quotes_and_collapse(text: str) -> str:
    """Remove quote lines (starting with >) and collapse whitespace."""
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    collapsed = " ".join(" ".join(lines).split())
    return collapsed


def _parse_address_header(raw: str) -> list[str]:
    """Split a comma-separated address header into a list of stripped strings."""
    if not raw:
        return []
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def _walk_mime(msg: Message) -> tuple[str, str | None, list[AttachmentMeta]]:
    """Walk a parsed email.Message and extract plain text, HTML, and attachment metadata.

    Returns:
        (body_plain, body_html, attachments)
    """
    body_plain = ""
    body_html: str | None = None
    attachments: list[AttachmentMeta] = []

    for part in msg.walk():
        content_disposition = part.get_content_disposition() or ""
        content_type = part.get_content_type()

        if content_disposition == "attachment":
            filename = part.get_filename() or "unnamed"
            payload = part.get_payload(decode=True)
            size = len(payload) if isinstance(payload, bytes) else 0
            attachments.append(
                AttachmentMeta(
                    filename=filename,
                    content_type=content_type,
                    size_bytes=size,
                )
            )
        elif content_type == "text/plain" and not body_plain:
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = part.get_content_charset() or "utf-8"
                try:
                    body_plain = payload.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    body_plain = payload.decode("utf-8", errors="replace")
        elif content_type == "text/html" and body_html is None:
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = part.get_content_charset() or "utf-8"
                try:
                    body_html = payload.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    body_html = payload.decode("utf-8", errors="replace")

    return body_plain, body_html, attachments


def _load_parsed_message(nm_msg: Any) -> Message:
    """Load and parse the raw MIME file for a notmuch message object."""
    # notmuch2 Message.filenames() returns an iterator of pathlib.Path objects
    try:
        filenames = list(nm_msg.filenames())
    except Exception as exc:
        raise DatabaseError(f"Could not read filenames for message: {exc}") from exc

    if not filenames:
        raise DatabaseError("Message has no associated files on disk.")

    file_path = filenames[0]
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        raise DatabaseError(f"Could not read message file {file_path}: {exc}") from exc

    return email.message_from_bytes(raw, policy=email.policy.compat32)


def _build_snippet(nm_msg: Any) -> str:
    """Extract snippet from the newest message's text/plain body."""
    try:
        parsed = _load_parsed_message(nm_msg)
    except DatabaseError:
        return ""
    body_plain, _, _ = _walk_mime(parsed)
    cleaned = _strip_quotes_and_collapse(body_plain)
    return cleaned[:200]


def _get_gmail_thread_id(nm_msg: Any) -> str | None:
    """Parse the X-GM-THRID header from the first message in a thread."""
    try:
        raw = nm_msg.header("X-GM-THRID")
    except (KeyError, Exception):
        return None
    val = raw.strip() if raw else ""
    return val if val else None


def _get_attachment_metas(nm_msg: Any) -> list[AttachmentMeta]:
    """Return attachment metadata list for a message without loading content."""
    try:
        parsed = _load_parsed_message(nm_msg)
    except DatabaseError:
        return []
    _, _, attachments = _walk_mime(parsed)
    return attachments


class Database:
    """Thin wrapper around the notmuch2 Python bindings."""

    def __init__(self, path: str | None = None) -> None:
        """Open the notmuch database.

        Args:
            path: Explicit DB path. If None, discovered via
                  ``notmuch config get database.path``.

        Raises:
            DatabaseError: If the database cannot be opened.
        """
        resolved = path if path is not None else _resolve_db_path()
        try:
            self._db: notmuch2.Database = notmuch2.Database(
                resolved,
                mode=notmuch2.Database.MODE.READ_WRITE,
            )
        except Exception as exc:
            raise DatabaseError(f"Could not open notmuch database at {resolved!r}: {exc}") from exc

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def query_threads(
        self,
        query: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ThreadSummary]:
        """Run a notmuch query and return a window of thread summaries.

        Args:
            query: A notmuch search query string.
            offset: Number of threads to skip from the start of results.
            limit: Maximum number of threads to return.

        Returns:
            A list of ThreadSummary dataclasses.
        """
        try:
            thread_iter = self._db.threads(query)
        except Exception as exc:
            raise DatabaseError(f"Query failed for {query!r}: {exc}") from exc

        summaries: list[ThreadSummary] = []
        for idx, thread in enumerate(thread_iter):
            if idx < offset:
                continue
            if len(summaries) >= limit:
                break

            # Collect all messages to find newest for snippet/attachment/gmail id
            try:
                all_messages = list(thread)
            except Exception:
                all_messages = []

            newest_msg = all_messages[-1] if all_messages else None
            first_msg = all_messages[0] if all_messages else None

            snippet = _build_snippet(newest_msg) if newest_msg is not None else ""
            gmail_thread_id = _get_gmail_thread_id(first_msg) if first_msg is not None else None

            try:
                authors_raw: str = thread.authors
                newest_date: int = int(thread.last)
                tags: frozenset[str] = frozenset(thread.tags)
                subject: str = thread.subject
                thread_id: str = thread.threadid
                message_count: int = len(thread)
            except Exception as exc:
                log.warning("Skipping malformed thread: %s", exc)
                continue

            summaries.append(
                ThreadSummary(
                    thread_id=thread_id,
                    subject=subject,
                    authors=_parse_authors(authors_raw),
                    newest_date=newest_date,
                    message_count=message_count,
                    tags=tags,
                    snippet=snippet,
                    gmail_thread_id=gmail_thread_id or "",
                )
            )

        return summaries

    def count_threads(self, query: str) -> int:
        """Return the total thread count for a query (fast Xapian count).

        Args:
            query: A notmuch search query string.

        Returns:
            Integer count of matching threads.

        Raises:
            DatabaseError: If the count query fails.
        """
        try:
            return self._db.count_threads(query)  # type: ignore[no-any-return]
        except Exception as exc:
            raise DatabaseError(f"count_threads failed for {query!r}: {exc}") from exc

    def get_thread_messages(self, thread_id: str) -> list[MessageDetail]:
        """Return all messages in a thread, ordered chronologically.

        Args:
            thread_id: The notmuch thread identifier.

        Returns:
            List of MessageDetail dataclasses sorted by date ascending.

        Raises:
            DatabaseError: If the thread cannot be retrieved.
        """
        query = f"thread:{thread_id}"
        try:
            thread_iter = self._db.threads(query)
        except Exception as exc:
            raise DatabaseError(f"get_thread_messages failed for {thread_id!r}: {exc}") from exc

        threads = list(thread_iter)
        if not threads:
            return []

        thread = threads[0]
        try:
            nm_messages = list(thread)
        except Exception as exc:
            raise DatabaseError(
                f"Could not iterate messages in thread {thread_id!r}: {exc}"
            ) from exc

        # Sort by date ascending
        with contextlib.suppress(Exception):
            nm_messages.sort(key=lambda m: int(m.date))

        result: list[MessageDetail] = []
        for nm_msg in nm_messages:
            try:
                parsed = _load_parsed_message(nm_msg)
            except DatabaseError as exc:
                log.warning("Skipping unreadable message: %s", exc)
                continue

            body_plain, body_html, attachments = _walk_mime(parsed)

            try:
                msg_id: str = nm_msg.messageid
                msg_thread_id: str = nm_msg.threadid
                msg_date: int = int(nm_msg.date)
                msg_tags: frozenset[str] = frozenset(nm_msg.tags)
            except Exception as exc:
                log.warning("Skipping message with missing fields: %s", exc)
                continue

            # Read headers from parsed MIME message
            try:
                from_header = parsed.get("From", "") or ""
                to_raw = parsed.get("To", "") or ""
                cc_raw = parsed.get("Cc", "") or ""
                subject = parsed.get("Subject", "") or ""
            except Exception:
                from_header = ""
                to_raw = ""
                cc_raw = ""
                subject = ""

            # Collect all headers into a dict
            headers: dict[str, str] = {}
            with contextlib.suppress(Exception):
                for key in parsed:
                    if key not in headers:
                        headers[key] = parsed.get(key, "") or ""

            result.append(
                MessageDetail(
                    message_id=msg_id,
                    thread_id=msg_thread_id,
                    from_=from_header,
                    to=_parse_address_header(to_raw),
                    cc=_parse_address_header(cc_raw),
                    date=msg_date,
                    subject=subject,
                    headers=headers,
                    body_plain=body_plain,
                    body_html=body_html,
                    tags=msg_tags,
                    attachments=attachments,
                )
            )

        return result

    # ------------------------------------------------------------------
    # Tag mutation methods
    # ------------------------------------------------------------------

    def add_tags(self, thread_id: str, tags: list[str]) -> None:
        """Add tags to every message in a thread.

        Args:
            thread_id: The notmuch thread identifier.
            tags: List of tag strings to add.

        Raises:
            DatabaseError: If the tags cannot be applied.
        """
        try:
            with self._db.atomic():
                for nm_msg in self._iter_thread_messages(thread_id):
                    for tag in tags:
                        nm_msg.tags.add(tag)
        except DatabaseError:
            raise
        except Exception as exc:
            raise DatabaseError(f"add_tags failed for thread {thread_id!r}: {exc}") from exc

    def remove_tags(self, thread_id: str, tags: list[str]) -> None:
        """Remove tags from every message in a thread.

        Args:
            thread_id: The notmuch thread identifier.
            tags: List of tag strings to remove.

        Raises:
            DatabaseError: If the tags cannot be removed.
        """
        try:
            with self._db.atomic():
                for nm_msg in self._iter_thread_messages(thread_id):
                    for tag in tags:
                        nm_msg.tags.discard(tag)
        except DatabaseError:
            raise
        except Exception as exc:
            raise DatabaseError(f"remove_tags failed for thread {thread_id!r}: {exc}") from exc

    def _iter_thread_messages(self, thread_id: str) -> list[Any]:
        """Return all raw notmuch2 message objects in a thread.

        Args:
            thread_id: The notmuch thread identifier.

        Returns:
            List of raw notmuch2 Message objects.

        Raises:
            DatabaseError: If the thread cannot be found.
        """
        query = f"thread:{thread_id}"
        try:
            thread_iter = self._db.threads(query)
            threads = list(thread_iter)
        except Exception as exc:
            raise DatabaseError(f"Could not query thread {thread_id!r}: {exc}") from exc
        if not threads:
            return []
        try:
            return list(threads[0])
        except Exception as exc:
            raise DatabaseError(
                f"Could not iterate messages in thread {thread_id!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Attachment content retrieval
    # ------------------------------------------------------------------

    def get_attachment_content(self, message_id: str, filename: str) -> bytes:
        """Extract attachment bytes from the MIME tree of a message.

        Args:
            message_id: The notmuch message-id string.
            filename: The attachment filename to find.

        Returns:
            Raw bytes of the attachment.

        Raises:
            DatabaseError: If the message or attachment cannot be found.
        """
        try:
            nm_msg = self._db.find(message_id)
        except KeyError as exc:
            raise DatabaseError(f"Message not found: {message_id!r}") from exc
        except Exception as exc:
            raise DatabaseError(f"Could not look up message {message_id!r}: {exc}") from exc

        parsed = _load_parsed_message(nm_msg)

        for part in parsed.walk():
            if part.get_content_disposition() == "attachment":
                part_filename = part.get_filename() or ""
                if part_filename == filename:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        return payload
                    return b""

        raise DatabaseError(
            f"Attachment {filename!r} not found in message {message_id!r}"
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the notmuch database handle."""
        try:
            self._db.close()
        except Exception as exc:
            log.warning("Error closing notmuch database: %s", exc)

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
