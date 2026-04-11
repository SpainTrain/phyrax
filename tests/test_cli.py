"""Tests for phyrax.cli — Typer entrypoint (E10-5)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import phyrax.config as config_module
from phyrax.cli import app
from phyrax.config import Bundle, BundleRule, PhyraxConfig
from tests.fixtures.maildir_builder import MaildirFixture

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bare_id(full_thread_id: str) -> str:
    """Strip ``thread:`` prefix from thread IDs stored in MaildirFixture."""
    return full_thread_id.removeprefix("thread:")


def _make_config(
    tmp_maildir: MaildirFixture,
    *,
    bundles: list[Bundle] | None = None,
) -> PhyraxConfig:
    """Build a PhyraxConfig suitable for CLI tests."""
    return PhyraxConfig(
        identity={"primary": "test@example.com", "aliases": []},  # type: ignore[arg-type]
        ai={"agent_command": "echo"},  # type: ignore[arg-type]
        bundles=bundles or [],
        compose={"include_quote": True},  # type: ignore[arg-type]
    )


def _newsletters_bundle() -> Bundle:
    """Bundle that matches threads tagged ``newsletters``."""
    return Bundle(
        name="Newsletters",
        label="newsletters",
        rules=[BundleRule(field="from", operator="contains", value="substack.com")],
        priority=40,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def patched_env(
    tmp_maildir: MaildirFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Set up the environment expected by CLI commands.

    - Sets NOTMUCH_CONFIG so Database() picks up the fixture maildir.
    - Patches LOCKFILE to a temp path so tests don't touch real system state.
    - Returns a dict with useful references.
    """
    test_lockfile = tmp_path / "phr-test.lock"
    test_drafts_dir = tmp_path / "drafts"
    test_drafts_dir.mkdir(parents=True)

    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))
    monkeypatch.setattr(config_module, "LOCKFILE", test_lockfile)
    monkeypatch.setattr(config_module, "DRAFTS_DIR", test_drafts_dir)

    return {
        "maildir": tmp_maildir,
        "lockfile": test_lockfile,
        "drafts_dir": test_drafts_dir,
    }


# ---------------------------------------------------------------------------
# phr status
# ---------------------------------------------------------------------------


def test_status_exit_code_zero(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr status must exit 0 and emit valid JSON."""
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, dict)


def test_status_json_schema(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr status JSON must contain all required E10-1 top-level keys."""
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "inbox_total" in data
    assert "inbox_unread" in data
    assert "bundles" in data
    assert "unbundled" in data
    assert "drafts_pending" in data


def test_status_inbox_total_matches_fixture(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr status inbox_total must equal 10 (the full fixture maildir)."""
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["inbox_total"] == 10


def test_status_bundle_entries_match_config(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr status bundles list must have one entry per configured bundle."""
    cfg = _make_config(tmp_maildir, bundles=[_newsletters_bundle()])
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data["bundles"]) == 1
    entry = data["bundles"][0]
    assert "name" in entry
    assert "count" in entry
    assert "unread" in entry
    assert entry["name"] == "Newsletters"


def test_status_unbundled_no_bundles(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """When no bundles are configured, unbundled must equal inbox_total."""
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["unbundled"] == data["inbox_total"]


def test_status_works_regardless_of_lockfile(
    tmp_maildir: MaildirFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """phr status (read command) must succeed even when the lockfile is present."""
    test_lockfile = tmp_path / "phr-test.lock"
    test_lockfile.write_text(str(os.getpid()), encoding="utf-8")

    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))
    monkeypatch.setattr(config_module, "LOCKFILE", test_lockfile)

    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# phr list (default)
# ---------------------------------------------------------------------------


def test_list_default_returns_inbox_threads(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr list (no args) must return exactly 10 inbox threads from the fixture."""
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    threads = json.loads(result.output)
    assert isinstance(threads, list)
    assert len(threads) == 10


def test_list_thread_object_schema(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """Each thread returned by phr list must have the required fields."""
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    threads = json.loads(result.output)
    required_keys = {
        "thread_id",
        "subject",
        "authors",
        "date_unix",
        "tags",
        "snippet",
        "gmail_thread_id",
    }
    for t in threads:
        assert required_keys <= set(t.keys()), f"Missing keys in thread: {set(t.keys())}"


def test_list_default_works_regardless_of_lockfile(
    tmp_maildir: MaildirFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """phr list (read command) must succeed even when the lockfile is held."""
    test_lockfile = tmp_path / "phr-test.lock"
    test_lockfile.write_text(str(os.getpid()), encoding="utf-8")

    monkeypatch.setenv("NOTMUCH_CONFIG", str(tmp_maildir.notmuch_config))
    monkeypatch.setattr(config_module, "LOCKFILE", test_lockfile)

    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# phr list --bundle=Newsletters
# ---------------------------------------------------------------------------


def test_list_bundle_newsletters_returns_one_thread(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr list --bundle=Newsletters must return all newsletters-tagged threads."""
    cfg = _make_config(tmp_maildir, bundles=[_newsletters_bundle()])
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["list", "--bundle=Newsletters"])
    assert result.exit_code == 0, result.output
    threads = json.loads(result.output)
    # Fixture has 2 newsletters threads: newsletter@substack.com and noreply@notion.so
    assert len(threads) == 2
    assert all("newsletters" in t["tags"] for t in threads)


def test_list_bundle_unknown_exits_1(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr list --bundle=DoesNotExist must exit 1."""
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["list", "--bundle=DoesNotExist"])
    assert result.exit_code == 1


def test_list_query_override(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr list --query='tag:alerts' must return all alerts-tagged threads."""
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["list", "--query=tag:alerts"])
    assert result.exit_code == 0, result.output
    threads = json.loads(result.output)
    # Fixture has 2 alerts threads: alerts@example.com and support@stripe.com
    assert len(threads) == 2
    assert all("alerts" in t["tags"] for t in threads)


# ---------------------------------------------------------------------------
# phr archive
# ---------------------------------------------------------------------------


def test_archive_removes_inbox_tag(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr archive must remove the inbox tag from the target thread."""
    thread_id = _bare_id(tmp_maildir.thread_ids["friend"])
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["archive", thread_id])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert data["thread_id"] == thread_id
    assert "inbox" not in data["tags"]


def test_archive_requery_confirms_removal(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After phr archive, querying tag:inbox must not return that thread."""
    from phyrax.database import Database

    thread_id = _bare_id(tmp_maildir.thread_ids["boss"])
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["archive", thread_id])
    assert result.exit_code == 0, result.output

    # Independently verify inbox no longer contains the thread
    with Database(path=str(tmp_maildir.maildir)) as db:
        remaining = db.query_threads(f"thread:{thread_id} tag:inbox")
    assert len(remaining) == 0


def test_archive_fails_with_exit_2_when_lockfile_held(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr archive must exit 2 when the PID lockfile is pre-held."""
    lockfile: Path = patched_env["lockfile"]
    lockfile.write_text("99999", encoding="utf-8")

    thread_id = _bare_id(tmp_maildir.thread_ids["alerts"])
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["archive", thread_id])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# phr tag
# ---------------------------------------------------------------------------


def test_tag_add_applies_tag(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr tag +foo must add the foo tag to the thread."""
    thread_id = _bare_id(tmp_maildir.thread_ids["docs"])
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["tag", thread_id, "+foo"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert "foo" in data["tags"]


def test_tag_remove_removes_tag(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr tag -unread must remove the unread tag from the thread.

    The ``--`` sentinel is required so that Typer/Click does not interpret
    ``-unread`` as a short option flag.
    """
    thread_id = _bare_id(tmp_maildir.thread_ids["newsletters"])
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["tag", thread_id, "--", "-unread"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "unread" not in data["tags"]


def test_tag_add_and_remove_together(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr tag +foo -inbox must add foo and remove inbox in one invocation.

    The ``--`` sentinel is required before dash-prefixed tag changes.
    """
    thread_id = _bare_id(tmp_maildir.thread_ids["alerts"])
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["tag", thread_id, "--", "+foo", "-inbox"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "foo" in data["tags"]
    assert "inbox" not in data["tags"]


def test_tag_invalid_prefix_exits_1(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr tag with a tag that lacks + or - prefix must exit 1."""
    thread_id = _bare_id(tmp_maildir.thread_ids["boss"])
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["tag", thread_id, "noprefixhere"])
    assert result.exit_code == 1


def test_tag_fails_with_exit_2_when_lockfile_held(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr tag must exit 2 when the PID lockfile is pre-held."""
    lockfile: Path = patched_env["lockfile"]
    lockfile.write_text("99999", encoding="utf-8")

    thread_id = _bare_id(tmp_maildir.thread_ids["alerts"])
    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(app, ["tag", thread_id, "+foo"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# phr compose
# ---------------------------------------------------------------------------


def test_compose_reads_body_from_stdin(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr compose must read the body from stdin when --body=- (default)."""
    drafts_dir: Path = patched_env["drafts_dir"]
    body_text = "Hello from test stdin!"
    cfg = _make_config(tmp_maildir)

    with (
        patch("phyrax.cli.PhyraxConfig") as mock_cls,
        patch("phyrax.composer.DRAFTS_DIR", drafts_dir),
        patch("phyrax.config.DRAFTS_DIR", drafts_dir),
    ):
        mock_cls.load.return_value = cfg
        result = runner.invoke(
            app,
            ["compose", "--to=recipient@example.com", "--subject=Test"],
            input=body_text,
        )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert "draft_id" in data
    assert "path" in data


def test_compose_creates_draft_file(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr compose must write a draft file to DRAFTS_DIR."""
    drafts_dir: Path = patched_env["drafts_dir"]
    cfg = _make_config(tmp_maildir)

    with (
        patch("phyrax.cli.PhyraxConfig") as mock_cls,
        patch("phyrax.composer.DRAFTS_DIR", drafts_dir),
        patch("phyrax.config.DRAFTS_DIR", drafts_dir),
    ):
        mock_cls.load.return_value = cfg
        result = runner.invoke(
            app,
            ["compose", "--to=someone@example.com", "--subject=Hello"],
            input="Draft body content.",
        )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    draft_path = Path(data["path"])
    assert draft_path.exists(), f"Draft file not found: {draft_path}"
    content = draft_path.read_text(encoding="utf-8")
    assert "Draft body content." in content


def test_compose_draft_file_has_rfc5322_headers(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """The draft file written by phr compose must contain RFC 5322 headers."""
    drafts_dir: Path = patched_env["drafts_dir"]
    cfg = _make_config(tmp_maildir)

    with (
        patch("phyrax.cli.PhyraxConfig") as mock_cls,
        patch("phyrax.composer.DRAFTS_DIR", drafts_dir),
        patch("phyrax.config.DRAFTS_DIR", drafts_dir),
    ):
        mock_cls.load.return_value = cfg
        result = runner.invoke(
            app,
            ["compose", "--to=person@example.com", "--subject=Subject Line"],
            input="Body here.",
        )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    draft_path = Path(data["path"])
    content = draft_path.read_text(encoding="utf-8")
    assert "From:" in content
    assert "To:" in content
    assert "Subject:" in content


def test_compose_fails_with_exit_2_when_lockfile_held(
    patched_env: dict[str, Any],
    tmp_maildir: MaildirFixture,
) -> None:
    """phr compose must exit 2 when the PID lockfile is pre-held."""
    lockfile: Path = patched_env["lockfile"]
    lockfile.write_text("99999", encoding="utf-8")

    cfg = _make_config(tmp_maildir)
    with patch("phyrax.cli.PhyraxConfig") as mock_cls:
        mock_cls.load.return_value = cfg
        result = runner.invoke(
            app,
            ["compose", "--to=a@b.com", "--subject=S"],
            input="body",
        )
    assert result.exit_code == 2
