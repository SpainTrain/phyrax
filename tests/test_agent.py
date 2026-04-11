"""Tests for phyrax.agent — AI subprocess management."""

from __future__ import annotations

from pathlib import Path

import pytest

from phyrax.agent import (
    AgentResult,
    compile_prompt,
    run_agent,
)
from phyrax.exceptions import AgentError
from phyrax.models import AttachmentMeta, MessageDetail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(**overrides: object) -> MessageDetail:
    """Return a MessageDetail with sensible defaults, allowing field overrides."""
    defaults: dict[str, object] = dict(
        message_id="<test@fixture>",
        thread_id="thread1",
        from_="sender@example.com",
        to=["me@example.com"],
        cc=[],
        date=1_735_732_800,
        subject="Test Subject",
        headers={"X-Custom": "should-be-excluded"},
        body_plain="Hello world\n> quoted line\nmore text",
        body_html=None,
        tags=frozenset({"inbox", "unread"}),
        attachments=[],
    )
    defaults.update(overrides)
    return MessageDetail(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# compile_prompt — XML structure
# ---------------------------------------------------------------------------


def test_compile_prompt_returns_existing_file() -> None:
    """compile_prompt returns a Path that exists on disk."""
    msg = _make_message()
    path = compile_prompt("Summarise this email.", msg)
    try:
        assert path.exists()
        assert path.is_file()
    finally:
        path.unlink(missing_ok=True)


def test_compile_prompt_xml_blocks_present_in_order() -> None:
    """Output contains <system>, <user_prompt>, <email_payload> in that order.

    The system prompt text itself mentions <email_payload>, so we look for the
    closing </system> tag to locate where the top-level blocks start, then find
    the top-level <user_prompt> and <email_payload> opening tags after it.
    """
    msg = _make_message()
    path = compile_prompt("Draft a reply.", msg)
    try:
        text = path.read_text(encoding="utf-8")
        sys_open = text.index("<system>")
        sys_close = text.index("</system>")
        # <user_prompt> must come after </system>
        user_pos = text.index("<user_prompt>", sys_close)
        # <email_payload> (top-level block) must come after <user_prompt>
        payload_pos = text.index("<email_payload>", user_pos)
        assert sys_open < sys_close < user_pos < payload_pos
    finally:
        path.unlink(missing_ok=True)


def test_compile_prompt_system_block_content() -> None:
    """<system> block contains the Phyrax injection-defence prompt."""
    msg = _make_message()
    path = compile_prompt("Any prompt.", msg)
    try:
        text = path.read_text(encoding="utf-8")
        assert "You are Phyrax" in text
        assert "<email_payload>" in text  # referenced in system prompt
    finally:
        path.unlink(missing_ok=True)


def test_compile_prompt_user_prompt_block_content() -> None:
    """<user_prompt> block contains the exact user_prompt string."""
    user_prompt = "Please triage this message."
    msg = _make_message()
    path = compile_prompt(user_prompt, msg)
    try:
        text = path.read_text(encoding="utf-8")
        assert f"<user_prompt>\n{user_prompt}\n</user_prompt>" in text
    finally:
        path.unlink(missing_ok=True)


def test_compile_prompt_email_payload_block_present() -> None:
    """<email_payload> block is closed with </email_payload>."""
    msg = _make_message()
    path = compile_prompt("Check it.", msg)
    try:
        text = path.read_text(encoding="utf-8")
        assert "<email_payload>" in text
        assert "</email_payload>" in text
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Header filtering
# ---------------------------------------------------------------------------


def test_compile_prompt_allowed_headers_present() -> None:
    """From, To, Cc, Date, Subject, Message-ID appear in email_payload."""
    msg = _make_message(
        from_="alice@example.com",
        to=["bob@example.com"],
        cc=["carol@example.com"],
        subject="Hello",
        message_id="<abc123@example.com>",
    )
    path = compile_prompt("Read this.", msg)
    try:
        text = path.read_text(encoding="utf-8")
        payload_start = text.index("<email_payload>")
        payload = text[payload_start:]
        assert "From: alice@example.com" in payload
        assert "To: bob@example.com" in payload
        assert "Cc: carol@example.com" in payload
        assert "Subject: Hello" in payload
        assert "Message-ID: <abc123@example.com>" in payload
        assert "Date:" in payload
    finally:
        path.unlink(missing_ok=True)


def test_compile_prompt_disallowed_headers_excluded() -> None:
    """Headers not in the allowlist (e.g. X-Custom) do not appear in the payload."""
    msg = _make_message(headers={"X-Custom": "secret-value", "DKIM-Signature": "v=1"})
    path = compile_prompt("Analyse.", msg)
    try:
        text = path.read_text(encoding="utf-8")
        payload_start = text.index("<email_payload>")
        payload = text[payload_start:]
        assert "X-Custom" not in payload
        assert "DKIM-Signature" not in payload
        assert "secret-value" not in payload
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Quote stripping
# ---------------------------------------------------------------------------


def test_compile_prompt_strips_quoted_lines_by_default() -> None:
    """Lines starting with '>' are removed when require_full_context is False."""
    msg = _make_message(body_plain="Hello\n> old reply\n> another quote\nNew text")
    path = compile_prompt("Summarise.", msg)
    try:
        text = path.read_text(encoding="utf-8")
        payload_start = text.index("<email_payload>")
        payload = text[payload_start:]
        assert "> old reply" not in payload
        assert "> another quote" not in payload
        assert "Hello" in payload
        assert "New text" in payload
    finally:
        path.unlink(missing_ok=True)


def test_compile_prompt_require_full_context_retains_quotes() -> None:
    """Lines starting with '>' are kept when require_full_context=True."""
    msg = _make_message(body_plain="Hello\n> old reply\nNew text")
    path = compile_prompt("Summarise.", msg, require_full_context=True)
    try:
        text = path.read_text(encoding="utf-8")
        payload_start = text.index("<email_payload>")
        payload = text[payload_start:]
        assert "> old reply" in payload
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Attachment handling
# ---------------------------------------------------------------------------


def test_compile_prompt_attachments_stripped_by_default() -> None:
    """Attachments are represented with action='stripped_by_phyrax' by default."""
    att = AttachmentMeta(filename="report.pdf", content_type="application/pdf", size_bytes=1024)
    msg = _make_message(attachments=[att])
    path = compile_prompt("Check attachments.", msg)
    try:
        text = path.read_text(encoding="utf-8")
        assert "report.pdf" in text
        assert "action='stripped_by_phyrax'" in text
        assert "action='inline_base64'" not in text
    finally:
        path.unlink(missing_ok=True)


def test_compile_prompt_attachment_tag_contains_mimetype() -> None:
    """Stripped attachment tag includes the correct mimetype attribute."""
    att = AttachmentMeta(filename="image.png", content_type="image/png", size_bytes=512)
    msg = _make_message(attachments=[att])
    path = compile_prompt("Look at this.", msg)
    try:
        text = path.read_text(encoding="utf-8")
        assert "mimetype='image/png'" in text
    finally:
        path.unlink(missing_ok=True)


def test_compile_prompt_allow_attachments_shows_inline_action() -> None:
    """With allow_attachments=True, attachment tag shows action='inline_base64'."""
    att = AttachmentMeta(
        filename="doc.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=2048,
    )
    msg = _make_message(attachments=[att])
    path = compile_prompt("Analyse doc.", msg, allow_attachments=True)
    try:
        text = path.read_text(encoding="utf-8")
        assert "action='inline_base64'" in text
        assert "action='stripped_by_phyrax'" not in text
    finally:
        path.unlink(missing_ok=True)


def test_compile_prompt_no_attachments_no_attachment_tags() -> None:
    """When a message has no attachments, no <attachment ... /> tags appear."""
    msg = _make_message(attachments=[])
    path = compile_prompt("No attachments.", msg)
    try:
        text = path.read_text(encoding="utf-8")
        assert "<attachment" not in text
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# run_agent — %s replacement in argv
# ---------------------------------------------------------------------------


def test_run_agent_percent_s_replaced_in_argv(tmp_path: Path) -> None:
    """The prompt file path replaces %s in the command; no literal %s in argv."""
    # Create a real prompt file so run_agent can find it.
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("test prompt content")

    # Use 'true' as the command so it succeeds immediately; %s is replaced.
    command = "true %s"
    result = run_agent(command, prompt_path)
    assert result.returncode == 0


def test_run_agent_prompt_path_in_constructed_command(tmp_path: Path) -> None:
    """The argv passed to the subprocess contains the actual prompt path string."""
    from phyrax.agent import _build_argv

    prompt_path = tmp_path / "myfile.txt"
    prompt_path.write_text("content")

    # Build argv and verify %s is gone and path is present.
    argv = _build_argv("cat %s", prompt_path)
    assert str(prompt_path) in " ".join(argv)
    assert "%s" not in " ".join(argv)


# ---------------------------------------------------------------------------
# run_agent — captured mode with mock_agent_command
# ---------------------------------------------------------------------------


def test_run_agent_captured_mode_returns_agent_result(
    tmp_path: Path, mock_agent_command: str
) -> None:
    """run_agent in captured mode returns an AgentResult with returncode=0."""
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("hello from test")

    # mock_agent_command echoes stdin; since no stdin is piped, stdout is empty.
    result = run_agent(mock_agent_command, prompt_path)
    assert isinstance(result, AgentResult)
    assert result.returncode == 0


def test_run_agent_captured_mode_is_default(tmp_path: Path, mock_agent_command: str) -> None:
    """run_agent defaults to RunMode.CAPTURED (no mode arg needed)."""
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("data")

    result = run_agent(mock_agent_command, prompt_path)
    assert result.returncode == 0
    # Captured mode populates stdout/stderr attributes.
    assert hasattr(result, "stdout")
    assert hasattr(result, "stderr")


# ---------------------------------------------------------------------------
# run_agent — fallback retry
# ---------------------------------------------------------------------------


def test_run_agent_uses_fallback_when_primary_fails(tmp_path: Path) -> None:
    """When primary exits nonzero, fallback command is used and succeeds."""
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("content")

    # Primary fails, fallback is 'true' (always succeeds).
    result = run_agent(
        "sh -c 'exit 1'",
        prompt_path,
        fallback_command="true",
    )
    assert result.returncode == 0


def test_run_agent_fallback_result_returned_not_primary(tmp_path: Path) -> None:
    """The returned AgentResult comes from the fallback, not the failing primary."""
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("data")

    # Primary fails; fallback echoes a known string.
    result = run_agent(
        "sh -c 'exit 1'",
        prompt_path,
        fallback_command="echo fallback_output",
    )
    assert result.returncode == 0
    assert "fallback_output" in result.stdout


# ---------------------------------------------------------------------------
# run_agent — AgentError on failure
# ---------------------------------------------------------------------------


def test_run_agent_raises_agent_error_when_primary_fails_no_fallback(
    tmp_path: Path,
) -> None:
    """run_agent raises AgentError when primary exits nonzero and no fallback is set."""
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("content")

    with pytest.raises(AgentError):
        run_agent("sh -c 'exit 1'", prompt_path)


def test_run_agent_raises_agent_error_when_both_primary_and_fallback_fail(
    tmp_path: Path,
) -> None:
    """AgentError is raised when both primary and fallback commands exit nonzero."""
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("content")

    with pytest.raises(AgentError):
        run_agent(
            "sh -c 'exit 1'",
            prompt_path,
            fallback_command="sh -c 'exit 2'",
        )


def test_run_agent_agent_error_message_contains_exit_code(tmp_path: Path) -> None:
    """AgentError message includes the nonzero exit code."""
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("content")

    with pytest.raises(AgentError, match="1"):
        run_agent("sh -c 'exit 1'", prompt_path)
