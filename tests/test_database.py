"""Tests for phyrax.database — notmuch abstraction layer."""

from __future__ import annotations

import pytest

from phyrax.database import Database
from phyrax.models import MessageDetail, ThreadSummary
from tests.fixtures.maildir_builder import MaildirFixture

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_db(tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch) -> Database:
    """Open a Database pointed at the fixture Maildir.

    Sets NOTMUCH_CONFIG so that any internal notmuch subprocess calls use the
    right config, and passes the maildir path directly to Database.__init__.
    """
    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))
    return Database(path=str(tmp_maildir.maildir))


def _bare_id(full_thread_id: str) -> str:
    """Strip the ``thread:`` prefix from a thread ID string.

    The fixture's ``thread_ids`` dict stores full strings like
    ``"thread:0000000000000003"`` (as returned by ``notmuch search
    --output=threads``), but ``Database`` methods expect the bare hex ID.
    """
    return full_thread_id.removeprefix("thread:")


# ---------------------------------------------------------------------------
# query_threads
# ---------------------------------------------------------------------------


def test_query_threads_returns_all_inbox(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """query_threads('tag:inbox') must return all 5 fixture threads."""
    with _open_db(tmp_maildir, monkeypatch) as db:
        results = db.query_threads("tag:inbox")
    assert len(results) == 5


def test_query_threads_returns_thread_summaries(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each element returned by query_threads must be a ThreadSummary."""
    with _open_db(tmp_maildir, monkeypatch) as db:
        results = db.query_threads("tag:inbox")
    assert all(isinstance(t, ThreadSummary) for t in results)


def test_query_threads_unknown_tag_returns_empty(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """query_threads for a tag that exists on no message must return []."""
    with _open_db(tmp_maildir, monkeypatch) as db:
        results = db.query_threads("tag:nonexistent_xyz")
    assert results == []


# ---------------------------------------------------------------------------
# count_threads
# ---------------------------------------------------------------------------


def test_count_threads_matches_query_threads_length(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """count_threads and len(query_threads) must agree for the same query."""
    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))
    with Database(path=str(tmp_maildir.maildir)) as db:
        count = db.count_threads("tag:inbox")
        results = db.query_threads("tag:inbox")
    assert count == len(results)


def test_count_threads_tag_alerts(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """count_threads('tag:alerts') must return 1 (only the alerts thread)."""
    with _open_db(tmp_maildir, monkeypatch) as db:
        assert db.count_threads("tag:alerts") == 1


# ---------------------------------------------------------------------------
# Pagination (offset + limit)
# ---------------------------------------------------------------------------


def test_pagination_returns_correct_slice(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """query_threads with offset=1, limit=2 returns exactly 2 threads skipping 1."""
    with _open_db(tmp_maildir, monkeypatch) as db:
        all_results = db.query_threads("tag:inbox", limit=100)
        page = db.query_threads("tag:inbox", offset=1, limit=2)

    assert len(page) == 2
    # The paged slice should match the slice of the full result
    assert page[0].thread_id == all_results[1].thread_id
    assert page[1].thread_id == all_results[2].thread_id


def test_pagination_offset_beyond_results_returns_empty(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """offset past the total result count must return an empty list."""
    with _open_db(tmp_maildir, monkeypatch) as db:
        results = db.query_threads("tag:inbox", offset=100, limit=10)
    assert results == []


def test_pagination_limit_zero_returns_empty(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """limit=0 must return an empty list."""
    with _open_db(tmp_maildir, monkeypatch) as db:
        results = db.query_threads("tag:inbox", limit=0)
    assert results == []


# ---------------------------------------------------------------------------
# get_thread_messages — chronological order
# ---------------------------------------------------------------------------


def test_get_thread_messages_chronological_order(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Messages in a multi-message thread must be sorted by date ascending."""
    boss_thread_id = _bare_id(tmp_maildir.thread_ids["boss"])  # 4 messages
    with _open_db(tmp_maildir, monkeypatch) as db:
        messages = db.get_thread_messages(boss_thread_id)

    assert len(messages) == 4
    dates = [m.date for m in messages]
    assert dates == sorted(dates), "Messages must be in ascending date order"


def test_get_thread_messages_returns_message_details(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_thread_messages must return MessageDetail instances."""
    alerts_thread_id = _bare_id(tmp_maildir.thread_ids["alerts"])
    with _open_db(tmp_maildir, monkeypatch) as db:
        messages = db.get_thread_messages(alerts_thread_id)

    assert len(messages) == 3
    assert all(isinstance(m, MessageDetail) for m in messages)


def test_get_thread_messages_correct_count_newsletters(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Newsletters thread (2 messages) must return exactly 2 MessageDetail objects."""
    newsletters_thread_id = _bare_id(tmp_maildir.thread_ids["newsletters"])
    with _open_db(tmp_maildir, monkeypatch) as db:
        messages = db.get_thread_messages(newsletters_thread_id)
    assert len(messages) == 2


def test_get_thread_messages_headers_populated(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each MessageDetail must have From, Subject, and a non-zero date."""
    alerts_thread_id = _bare_id(tmp_maildir.thread_ids["alerts"])
    with _open_db(tmp_maildir, monkeypatch) as db:
        messages = db.get_thread_messages(alerts_thread_id)

    for msg in messages:
        assert msg.from_ != ""
        assert msg.subject != ""
        assert msg.date > 0


def test_get_thread_messages_unknown_thread_returns_empty(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_thread_messages for a non-existent thread ID must return []."""
    with _open_db(tmp_maildir, monkeypatch) as db:
        messages = db.get_thread_messages("doesnotexist000")
    assert messages == []


# ---------------------------------------------------------------------------
# add_tags persistence
# ---------------------------------------------------------------------------


def test_add_tags_persists(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After add_tags, the thread must appear in a query for that tag."""
    friend_thread_id = _bare_id(tmp_maildir.thread_ids["friend"])
    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))

    with Database(path=str(tmp_maildir.maildir)) as db:
        # Confirm the tag is absent before adding
        before = db.query_threads("tag:custom_marker_test")
        assert len(before) == 0

        db.add_tags(friend_thread_id, ["custom_marker_test"])

        after = db.query_threads("tag:custom_marker_test")

    assert len(after) == 1
    assert after[0].thread_id == friend_thread_id


def test_add_tags_visible_in_thread_summary(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The new tag must appear in the returned ThreadSummary.tags frozenset."""
    boss_thread_id = _bare_id(tmp_maildir.thread_ids["boss"])
    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))

    with Database(path=str(tmp_maildir.maildir)) as db:
        db.add_tags(boss_thread_id, ["priority"])
        results = db.query_threads(f"thread:{boss_thread_id}")

    assert len(results) == 1
    assert "priority" in results[0].tags


# ---------------------------------------------------------------------------
# remove_tags persistence
# ---------------------------------------------------------------------------


def test_remove_tags_persists(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After remove_tags('inbox'), the thread must not appear in tag:inbox."""
    newsletters_thread_id = _bare_id(tmp_maildir.thread_ids["newsletters"])
    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))

    with Database(path=str(tmp_maildir.maildir)) as db:
        # Sanity: thread is currently in inbox
        before = db.query_threads(f"thread:{newsletters_thread_id} tag:inbox")
        assert len(before) == 1

        db.remove_tags(newsletters_thread_id, ["inbox"])

        after = db.query_threads(f"thread:{newsletters_thread_id} tag:inbox")

    assert len(after) == 0


def test_remove_tags_does_not_affect_other_threads(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing inbox from one thread must not remove it from others."""
    newsletters_thread_id = _bare_id(tmp_maildir.thread_ids["newsletters"])
    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))

    with Database(path=str(tmp_maildir.maildir)) as db:
        db.remove_tags(newsletters_thread_id, ["inbox"])
        remaining = db.query_threads("tag:inbox")

    # 5 threads total; 1 had inbox removed → 4 remain
    assert len(remaining) == 4


def test_remove_nonexistent_tag_is_safe(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing a tag that is not present must not raise an exception."""
    boss_thread_id = _bare_id(tmp_maildir.thread_ids["boss"])
    with _open_db(tmp_maildir, monkeypatch) as db:
        # Should not raise
        db.remove_tags(boss_thread_id, ["tag_that_was_never_applied"])


# ---------------------------------------------------------------------------
# get_attachment_content
# ---------------------------------------------------------------------------


def test_get_attachment_content_returns_bytes(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_attachment_content must return non-empty bytes for the PDF attachment."""
    docs_thread_id = _bare_id(tmp_maildir.thread_ids["docs"])
    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))

    with Database(path=str(tmp_maildir.maildir)) as db:
        # Retrieve the message ID for the docs thread
        messages = db.get_thread_messages(docs_thread_id)
        assert len(messages) == 1
        msg = messages[0]

        # Confirm the attachment metadata is present
        assert len(msg.attachments) == 1
        assert msg.attachments[0].filename == "document.pdf"

        content = db.get_attachment_content(msg.message_id, "document.pdf")

    assert isinstance(content, bytes)
    assert len(content) > 0


def test_get_attachment_content_starts_with_pdf_magic(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The returned bytes must begin with the PDF magic number %%PDF."""
    docs_thread_id = _bare_id(tmp_maildir.thread_ids["docs"])
    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))

    with Database(path=str(tmp_maildir.maildir)) as db:
        messages = db.get_thread_messages(docs_thread_id)
        msg = messages[0]
        content = db.get_attachment_content(msg.message_id, "document.pdf")

    assert content.startswith(b"%PDF"), (
        f"Expected PDF magic bytes, got: {content[:8]!r}"
    )


def test_get_attachment_content_wrong_filename_raises(
    tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_attachment_content with an unknown filename must raise DatabaseError."""
    from phyrax.exceptions import DatabaseError

    docs_thread_id = _bare_id(tmp_maildir.thread_ids["docs"])
    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))

    with Database(path=str(tmp_maildir.maildir)) as db:
        messages = db.get_thread_messages(docs_thread_id)
        msg = messages[0]
        with pytest.raises(DatabaseError):
            db.get_attachment_content(msg.message_id, "no_such_file.pdf")
