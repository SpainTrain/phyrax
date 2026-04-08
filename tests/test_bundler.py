"""Tests for phyrax.bundler — rule matching engine and tag applier."""

from __future__ import annotations

import pytest

from phyrax.bundler import (
    apply_bundle_tags,
    match_thread_to_bundle,
    sort_bundles,
)
from phyrax.config import Bundle, BundleRule, PhyraxConfig
from phyrax.database import Database
from tests.fixtures.maildir_builder import MaildirFixture

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bundle(
    name: str,
    label: str,
    rules: list[BundleRule],
    priority: int = 50,
) -> Bundle:
    return Bundle(name=name, label=label, rules=rules, priority=priority)


def _make_rule(
    field: str,
    operator: str,
    value: str | None = None,
) -> BundleRule:
    return BundleRule(field=field, operator=operator, value=value)  # type: ignore[arg-type]


def _open_db(tmp_maildir: MaildirFixture, monkeypatch: pytest.MonkeyPatch) -> Database:
    """Open a Database pointed at the fixture Maildir."""
    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))
    return Database(path=str(tmp_maildir.maildir))


def _bare_id(full_thread_id: str) -> str:
    return full_thread_id.removeprefix("thread:")


# ---------------------------------------------------------------------------
# sort_bundles
# ---------------------------------------------------------------------------


def test_sort_bundles_ascending_priority() -> None:
    """sort_bundles returns bundles ordered ascending by priority."""
    config = PhyraxConfig(
        bundles=[
            _make_bundle("C", "c", [_make_rule("from", "contains", "c")], priority=30),
            _make_bundle("A", "a", [_make_rule("from", "contains", "a")], priority=10),
            _make_bundle("B", "b", [_make_rule("from", "contains", "b")], priority=20),
        ]
    )
    sorted_bundles = sort_bundles(config)
    assert [b.priority for b in sorted_bundles] == [10, 20, 30]


def test_sort_bundles_stable_priority_ties() -> None:
    """sort_bundles preserves insertion order for bundles with equal priority."""
    config = PhyraxConfig(
        bundles=[
            _make_bundle("First", "first", [_make_rule("from", "contains", "x")], priority=50),
            _make_bundle("Second", "second", [_make_rule("from", "contains", "y")], priority=50),
            _make_bundle("Third", "third", [_make_rule("from", "contains", "z")], priority=50),
        ]
    )
    sorted_bundles = sort_bundles(config)
    assert [b.name for b in sorted_bundles] == ["First", "Second", "Third"]


def test_sort_bundles_empty_config() -> None:
    """sort_bundles on an empty bundle list returns an empty list."""
    config = PhyraxConfig(bundles=[])
    assert sort_bundles(config) == []


# ---------------------------------------------------------------------------
# _rule_matches via match_thread_to_bundle — contains operator
# ---------------------------------------------------------------------------


def test_contains_on_from_matches_substring() -> None:
    """A 'from contains newsletters' rule matches alice@newsletters.com."""
    headers = {"From": "alice@newsletters.com"}
    bundles = [
        _make_bundle(
            "Newsletters",
            "newsletters",
            [_make_rule("from", "contains", "newsletters")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None
    assert result.name == "Newsletters"


def test_contains_case_insensitive() -> None:
    """'contains' matching is case-insensitive."""
    headers = {"From": "Alice@NEWSLETTERS.COM"}
    bundles = [
        _make_bundle(
            "Newsletters",
            "newsletters",
            [_make_rule("from", "contains", "newsletters")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None


def test_contains_no_match() -> None:
    """'contains' does not match when the substring is absent."""
    headers = {"From": "boss@company.com"}
    bundles = [
        _make_bundle(
            "Newsletters",
            "newsletters",
            [_make_rule("from", "contains", "newsletters")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is None


def test_contains_on_subject() -> None:
    """'from contains' does not accidentally match the Subject header."""
    headers = {"From": "user@example.com", "Subject": "newsletters weekly"}
    bundles = [
        _make_bundle(
            "Newsletters",
            "newsletters",
            [_make_rule("from", "contains", "newsletters")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is None


# ---------------------------------------------------------------------------
# equals operator
# ---------------------------------------------------------------------------


def test_equals_exact_match() -> None:
    """'equals' matches when the header value equals the rule value (case-insensitive)."""
    headers = {"From": "boss@company.com"}
    bundles = [
        _make_bundle(
            "Boss",
            "boss",
            [_make_rule("from", "equals", "boss@company.com")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None
    assert result.name == "Boss"


def test_equals_case_insensitive() -> None:
    """'equals' comparison is case-insensitive per convention."""
    headers = {"From": "BOSS@COMPANY.COM"}
    bundles = [
        _make_bundle(
            "Boss",
            "boss",
            [_make_rule("from", "equals", "boss@company.com")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None


def test_equals_no_match_substring() -> None:
    """'equals' does not match when the value is only a substring of the header."""
    headers = {"From": "boss@company.com"}
    bundles = [
        _make_bundle(
            "Boss",
            "boss",
            [_make_rule("from", "equals", "company.com")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is None


def test_equals_no_match_different_value() -> None:
    """'equals' does not match when the full value differs."""
    headers = {"From": "other@example.com"}
    bundles = [
        _make_bundle(
            "Boss",
            "boss",
            [_make_rule("from", "equals", "boss@company.com")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is None


# ---------------------------------------------------------------------------
# matches (regex) operator
# ---------------------------------------------------------------------------


def test_matches_regex_basic() -> None:
    """'matches' uses re.search and matches a simple pattern."""
    headers = {"From": "alerts@example.com"}
    bundles = [
        _make_bundle(
            "Alerts",
            "alerts",
            [_make_rule("from", "matches", r"alerts@\w+\.com")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None
    assert result.name == "Alerts"


def test_matches_regex_case_insensitive() -> None:
    """'matches' is case-insensitive (re.IGNORECASE)."""
    headers = {"From": "ALERTS@EXAMPLE.COM"}
    bundles = [
        _make_bundle(
            "Alerts",
            "alerts",
            [_make_rule("from", "matches", r"alerts@example\.com")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None


def test_matches_regex_partial_match() -> None:
    """'matches' uses re.search, so partial (non-anchored) patterns match."""
    headers = {"Subject": "Alert: Server Down at 03:00"}
    bundles = [
        _make_bundle(
            "Alerts",
            "alerts",
            [_make_rule("subject", "matches", r"alert")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None


def test_matches_regex_no_match() -> None:
    """'matches' returns None when the regex does not match the header value."""
    headers = {"From": "friend@example.com"}
    bundles = [
        _make_bundle(
            "Alerts",
            "alerts",
            [_make_rule("from", "matches", r"^alerts@")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is None


# ---------------------------------------------------------------------------
# exists operator
# ---------------------------------------------------------------------------


def test_exists_on_list_id_present() -> None:
    """'exists' on header:List-Id matches a thread that has the header."""
    headers = {"From": "list@example.com", "List-Id": "<dev.lists.example.com>"}
    bundles = [
        _make_bundle(
            "Lists",
            "lists",
            [_make_rule("header:List-Id", "exists")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None
    assert result.name == "Lists"


def test_exists_on_list_id_absent() -> None:
    """'exists' on header:List-Id does not match a thread without that header."""
    headers = {"From": "friend@example.com"}
    bundles = [
        _make_bundle(
            "Lists",
            "lists",
            [_make_rule("header:List-Id", "exists")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is None


def test_exists_empty_string_counts_as_absent() -> None:
    """'exists' treats an empty header value as absent (falsy)."""
    headers = {"From": "friend@example.com", "List-Id": ""}
    bundles = [
        _make_bundle(
            "Lists",
            "lists",
            [_make_rule("header:List-Id", "exists")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is None


def test_exists_on_named_field_from() -> None:
    """'exists' works on named fields like 'from', not just 'header:' syntax."""
    headers = {"From": "someone@example.com"}
    bundles = [
        _make_bundle(
            "HasFrom",
            "hasfrom",
            [_make_rule("from", "exists")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


def test_priority_ordering_first_match_wins() -> None:
    """When two bundles could match, the one with lower priority number wins."""
    headers = {"From": "alice@newsletters.com"}
    bundles = [
        # priority 10 matches first
        _make_bundle(
            "HighPriority",
            "high",
            [_make_rule("from", "contains", "alice")],
            priority=10,
        ),
        _make_bundle(
            "LowPriority",
            "low",
            [_make_rule("from", "contains", "newsletters")],
            priority=20,
        ),
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None
    assert result.name == "HighPriority"


def test_priority_ordering_second_bundle_matches_when_first_does_not() -> None:
    """When the first bundle does not match, the second bundle is evaluated."""
    headers = {"From": "alice@newsletters.com"}
    bundles = [
        _make_bundle(
            "Alerts",
            "alerts",
            [_make_rule("from", "contains", "alerts")],
            priority=10,
        ),
        _make_bundle(
            "Newsletters",
            "newsletters",
            [_make_rule("from", "contains", "newsletters")],
            priority=20,
        ),
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None
    assert result.name == "Newsletters"


def test_priority_ties_resolved_by_config_order() -> None:
    """When two bundles share the same priority, config list order determines winner."""
    headers = {"From": "alice@example.com"}
    # Both match, same priority — first in list wins.
    bundles = [
        _make_bundle(
            "First",
            "first",
            [_make_rule("from", "contains", "alice")],
            priority=50,
        ),
        _make_bundle(
            "Second",
            "second",
            [_make_rule("from", "contains", "example")],
            priority=50,
        ),
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None
    assert result.name == "First"


# ---------------------------------------------------------------------------
# no-match returns None
# ---------------------------------------------------------------------------


def test_no_match_returns_none() -> None:
    """match_thread_to_bundle returns None when no bundle rule matches."""
    headers = {"From": "stranger@unknown.org", "Subject": "Random email"}
    bundles = [
        _make_bundle(
            "Newsletters",
            "newsletters",
            [_make_rule("from", "contains", "newsletters")],
        ),
        _make_bundle(
            "Alerts",
            "alerts",
            [_make_rule("from", "contains", "alerts")],
        ),
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is None


def test_no_match_empty_bundle_list() -> None:
    """match_thread_to_bundle with an empty bundle list always returns None."""
    headers = {"From": "alice@newsletters.com"}
    result = match_thread_to_bundle(headers, [])
    assert result is None


def test_no_match_missing_header() -> None:
    """A rule targeting a header absent from thread_headers does not match."""
    headers = {"From": "user@example.com"}
    bundles = [
        _make_bundle(
            "Lists",
            "lists",
            [_make_rule("header:List-Id", "contains", "lists")],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is None


# ---------------------------------------------------------------------------
# Multiple rules within a bundle (OR semantics)
# ---------------------------------------------------------------------------


def test_bundle_with_multiple_rules_matches_any() -> None:
    """Rules within a bundle are OR-combined: any matching rule triggers the bundle."""
    headers = {"From": "boss@company.com"}
    bundles = [
        _make_bundle(
            "Work",
            "work",
            [
                _make_rule("from", "contains", "alerts"),
                _make_rule("from", "contains", "company"),  # this one matches
            ],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is not None
    assert result.name == "Work"


def test_bundle_with_multiple_rules_no_match() -> None:
    """No rules in the bundle match — bundle does not match."""
    headers = {"From": "friend@example.com"}
    bundles = [
        _make_bundle(
            "Work",
            "work",
            [
                _make_rule("from", "contains", "alerts"),
                _make_rule("from", "contains", "company"),
            ],
        )
    ]
    result = match_thread_to_bundle(headers, bundles)
    assert result is None


# ---------------------------------------------------------------------------
# apply_bundle_tags — requires a real notmuch database
# ---------------------------------------------------------------------------


def test_apply_bundle_tags_adds_tag(
    tmp_maildir: MaildirFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """apply_bundle_tags adds the bundle label as a tag to the thread."""
    friend_thread_id = _bare_id(tmp_maildir.thread_ids["friend"])
    bundle = _make_bundle(
        "Friends",
        "friends",
        [_make_rule("from", "contains", "friend")],
    )
    with _open_db(tmp_maildir, monkeypatch) as db:
        # Confirm tag is absent before applying
        before = db.query_threads("tag:friends")
        assert len(before) == 0

        apply_bundle_tags(db, friend_thread_id, bundle)

        after = db.query_threads("tag:friends")

    assert len(after) == 1
    assert after[0].thread_id == friend_thread_id


def test_apply_bundle_tags_idempotent(
    tmp_maildir: MaildirFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling apply_bundle_tags twice on the same thread is a no-op the second time."""
    friend_thread_id = _bare_id(tmp_maildir.thread_ids["friend"])
    bundle = _make_bundle(
        "Friends",
        "friends",
        [_make_rule("from", "contains", "friend")],
    )
    with _open_db(tmp_maildir, monkeypatch) as db:
        apply_bundle_tags(db, friend_thread_id, bundle)
        apply_bundle_tags(db, friend_thread_id, bundle)  # second call: no-op

        results = db.query_threads("tag:friends")

    # Still exactly one thread with the tag — tag was not duplicated or removed.
    assert len(results) == 1
    assert results[0].thread_id == friend_thread_id


def test_apply_bundle_tags_tag_visible_in_thread_summary(
    tmp_maildir: MaildirFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After apply_bundle_tags, the label appears in the ThreadSummary.tags frozenset."""
    boss_thread_id = _bare_id(tmp_maildir.thread_ids["boss"])
    bundle = _make_bundle(
        "Work",
        "work",
        [_make_rule("from", "contains", "boss")],
    )
    with _open_db(tmp_maildir, monkeypatch) as db:
        apply_bundle_tags(db, boss_thread_id, bundle)
        results = db.query_threads(f"thread:{boss_thread_id}")

    assert len(results) == 1
    assert "work" in results[0].tags


def test_apply_bundle_tags_does_not_remove_existing_tags(
    tmp_maildir: MaildirFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """apply_bundle_tags only adds the label tag; pre-existing tags are preserved."""
    alerts_thread_id = _bare_id(tmp_maildir.thread_ids["alerts"])
    bundle = _make_bundle(
        "Monitoring",
        "monitoring",
        [_make_rule("from", "contains", "alerts")],
    )
    with _open_db(tmp_maildir, monkeypatch) as db:
        apply_bundle_tags(db, alerts_thread_id, bundle)
        results = db.query_threads(f"thread:{alerts_thread_id}")

    assert len(results) == 1
    thread = results[0]
    # Pre-existing tags must still be present
    assert "inbox" in thread.tags
    assert "unread" in thread.tags
    assert "alerts" in thread.tags
    # New tag added
    assert "monitoring" in thread.tags
