"""Tests for phyrax.composer — draft lifecycle."""

from __future__ import annotations

import stat
import textwrap
import uuid
from pathlib import Path

import pytest

from phyrax.composer import (
    _build_quote,
    _parse_draft,
    cleanup_draft,
    generate_draft,
    open_editor,
    pick_alias,
    recover_unsent_drafts,
    save_draft,
)
from phyrax.config import PhyraxConfig
from phyrax.exceptions import ComposeError
from phyrax.models import Draft, MessageDetail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(
    *,
    from_: str = "alice@example.com",
    to: list[str] | None = None,
    cc: list[str] | None = None,
    headers: dict[str, str] | None = None,
    body_plain: str = "Hello world",
) -> MessageDetail:
    return MessageDetail(
        message_id="<test-msg-id@example.com>",
        thread_id="thread-001",
        from_=from_,
        to=to or ["bob@example.com"],
        cc=cc or [],
        date=1712345678,
        subject="Test subject",
        headers=headers or {},
        body_plain=body_plain,
        body_html=None,
        tags=frozenset({"inbox"}),
        attachments=[],
    )


def _make_config(
    *,
    primary: str = "me@example.com",
    aliases: list[str] | None = None,
    include_quote: bool = True,
    agent_command: str = "echo reply-body",
) -> PhyraxConfig:
    return PhyraxConfig.model_validate(
        {
            "identity": {"primary": primary, "aliases": aliases or []},
            "ai": {"agent_command": agent_command},
            "compose": {"include_quote": include_quote},
        }
    )


def _make_draft(tmp_path: Path, **kwargs: object) -> Draft:
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    draft_uuid = str(uuid.uuid4())
    defaults: dict[str, object] = {
        "uuid": draft_uuid,
        "thread_id": "thread-001",
        "in_reply_to": "<orig@example.com>",
        "to": ["alice@example.com"],
        "cc": [],
        "subject": "Re: Test subject",
        "from_": "me@example.com",
        "body_markdown": "This is the reply body.",
        "cache_path": drafts_dir / f"{draft_uuid}.txt",
    }
    defaults.update(kwargs)
    return Draft(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# pick_alias
# ---------------------------------------------------------------------------


def test_pick_alias_returns_primary_when_no_aliases() -> None:
    msg = _make_message(to=["bob@example.com"])
    config = _make_config(primary="me@example.com", aliases=[])
    assert pick_alias(msg, config) == "me@example.com"


def test_pick_alias_matches_to_header() -> None:
    msg = _make_message(to=["work@example.com", "other@example.com"])
    config = _make_config(primary="home@example.com", aliases=["work@example.com"])
    assert pick_alias(msg, config) == "work@example.com"


def test_pick_alias_matches_cc_header() -> None:
    msg = _make_message(to=["other@example.com"], cc=["cc-alias@example.com"])
    config = _make_config(primary="home@example.com", aliases=["cc-alias@example.com"])
    assert pick_alias(msg, config) == "cc-alias@example.com"


def test_pick_alias_matches_delivered_to_header() -> None:
    msg = _make_message(
        to=["other@example.com"],
        headers={"Delivered-To": "delivered@example.com"},
    )
    config = _make_config(primary="home@example.com", aliases=["delivered@example.com"])
    assert pick_alias(msg, config) == "delivered@example.com"


def test_pick_alias_case_insensitive() -> None:
    msg = _make_message(to=["WORK@EXAMPLE.COM"])
    config = _make_config(primary="home@example.com", aliases=["work@example.com"])
    assert pick_alias(msg, config) == "work@example.com"


def test_pick_alias_returns_first_matching_alias() -> None:
    """When multiple aliases match, the first alias in config list wins."""
    msg = _make_message(to=["alias-b@example.com", "alias-a@example.com"])
    config = _make_config(
        primary="home@example.com",
        aliases=["alias-a@example.com", "alias-b@example.com"],
    )
    assert pick_alias(msg, config) == "alias-a@example.com"


# ---------------------------------------------------------------------------
# _build_quote
# ---------------------------------------------------------------------------


def test_build_quote_format() -> None:
    msg = _make_message(from_="alice@example.com", body_plain="Line one\nLine two")
    quote = _build_quote(msg)
    assert "alice@example.com wrote:" in quote
    assert "> Line one" in quote
    assert "> Line two" in quote


def test_build_quote_empty_body() -> None:
    msg = _make_message(body_plain="")
    quote = _build_quote(msg)
    assert "wrote:" in quote


# ---------------------------------------------------------------------------
# save_draft / _parse_draft round-trip
# ---------------------------------------------------------------------------


def test_save_and_parse_draft_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("phyrax.composer.DRAFTS_DIR", tmp_path / "drafts")
    import phyrax.composer as composer_mod

    monkeypatch.setattr(composer_mod, "DRAFTS_DIR", tmp_path / "drafts")

    draft = _make_draft(tmp_path)
    save_draft(draft)

    assert draft.cache_path.exists()
    parsed = _parse_draft(draft.cache_path)

    assert parsed.uuid == draft.uuid
    assert parsed.thread_id == draft.thread_id
    assert parsed.in_reply_to == draft.in_reply_to
    assert parsed.to == draft.to
    assert parsed.subject == draft.subject
    assert parsed.from_ == draft.from_
    assert parsed.body_markdown == draft.body_markdown


def test_save_draft_with_cc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("phyrax.composer.DRAFTS_DIR", tmp_path / "drafts")
    import phyrax.composer as composer_mod

    monkeypatch.setattr(composer_mod, "DRAFTS_DIR", tmp_path / "drafts")

    draft = _make_draft(tmp_path, cc=["cc1@example.com", "cc2@example.com"])
    save_draft(draft)

    parsed = _parse_draft(draft.cache_path)
    assert parsed.cc == ["cc1@example.com", "cc2@example.com"]


def test_parse_draft_raises_on_missing_blank_line(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.txt"
    bad_file.write_text("From: me@example.com\nSubject: Test\nNo blank line here", encoding="utf-8")
    with pytest.raises(ComposeError, match="no header/body separator"):
        _parse_draft(bad_file)


def test_parse_draft_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ComposeError, match="Cannot read draft file"):
        _parse_draft(tmp_path / "nonexistent.txt")


# ---------------------------------------------------------------------------
# recover_unsent_drafts
# ---------------------------------------------------------------------------


def test_recover_unsent_drafts_empty_when_no_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("phyrax.composer.DRAFTS_DIR", tmp_path / "nonexistent")
    import phyrax.composer as composer_mod

    monkeypatch.setattr(composer_mod, "DRAFTS_DIR", tmp_path / "nonexistent")
    assert recover_unsent_drafts() == []


def test_recover_unsent_drafts_returns_valid_drafts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    import phyrax.composer as composer_mod

    monkeypatch.setattr(composer_mod, "DRAFTS_DIR", drafts_dir)

    draft = _make_draft(tmp_path)
    save_draft(draft)

    recovered = recover_unsent_drafts()
    assert len(recovered) == 1
    assert recovered[0].uuid == draft.uuid


def test_recover_unsent_drafts_skips_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    import phyrax.composer as composer_mod

    monkeypatch.setattr(composer_mod, "DRAFTS_DIR", drafts_dir)

    # Good draft
    good = _make_draft(tmp_path)
    save_draft(good)

    # Malformed draft (no blank line separator)
    bad = drafts_dir / "bad.txt"
    bad.write_text("From: me@example.com\nSubject: Bad\nno blank line", encoding="utf-8")

    recovered = recover_unsent_drafts()
    assert len(recovered) == 1
    assert recovered[0].uuid == good.uuid


# ---------------------------------------------------------------------------
# cleanup_draft
# ---------------------------------------------------------------------------


def test_cleanup_draft_deletes_file(tmp_path: Path) -> None:
    draft = _make_draft(tmp_path)
    draft.cache_path.parent.mkdir(parents=True, exist_ok=True)
    draft.cache_path.write_text("content", encoding="utf-8")
    assert draft.cache_path.exists()

    cleanup_draft(draft)
    assert not draft.cache_path.exists()


def test_cleanup_draft_noop_when_file_missing(tmp_path: Path) -> None:
    draft = _make_draft(tmp_path)
    # cache_path does not exist — should not raise
    cleanup_draft(draft)


# ---------------------------------------------------------------------------
# open_editor
# ---------------------------------------------------------------------------


def test_open_editor_re_parses_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """open_editor should return a Draft reflecting any edits made."""
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    import phyrax.composer as composer_mod

    monkeypatch.setattr(composer_mod, "DRAFTS_DIR", drafts_dir)

    draft = _make_draft(tmp_path)
    save_draft(draft)

    # Use 'true' as EDITOR so the file is left unchanged.
    monkeypatch.setenv("EDITOR", "true")
    result = open_editor(draft)
    assert result.uuid == draft.uuid
    assert result.body_markdown == draft.body_markdown


# ---------------------------------------------------------------------------
# generate_draft
# ---------------------------------------------------------------------------


def test_generate_draft_uses_from_field_as_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate_draft should reply to the original sender (from_ field)."""
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    import phyrax.composer as composer_mod

    monkeypatch.setattr(composer_mod, "DRAFTS_DIR", drafts_dir)

    # Create a mock agent script that outputs a fixed reply body.
    script = tmp_path / "mock_agent.sh"
    script.write_text(
        textwrap.dedent("""\
            #!/usr/bin/env sh
            echo "This is the AI reply"
        """)
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    msg = _make_message(from_="alice@example.com", to=["me@example.com"])
    config = _make_config(
        primary="me@example.com",
        aliases=["me@example.com"],
        agent_command=f"{script} %s",
    )

    draft = generate_draft(msg, "Write a brief reply", config)

    assert draft.to == ["alice@example.com"]
    assert draft.subject == "Re: Test subject"
    assert draft.from_ == "me@example.com"
    assert "AI reply" in draft.body_markdown
