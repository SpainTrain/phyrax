"""Tests for phyrax.sender — pandoc rendering, MIME construction, gmi dispatch."""

from __future__ import annotations

import email
import subprocess
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from phyrax.exceptions import SendError
from phyrax.models import Draft
from phyrax.sender import preview_in_browser, render_html, send_reply

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_draft(tmp_path: Path, **kwargs: object) -> Draft:
    draft_id = str(uuid.uuid4())
    cache_path = tmp_path / f"{draft_id}.txt"
    defaults: dict[str, object] = {
        "uuid": draft_id,
        "thread_id": "tid-001",
        "in_reply_to": "<original@example.com>",
        "to": ["recipient@example.com"],
        "cc": [],
        "subject": "Re: Test Subject",
        "from_": "sender@example.com",
        "body_markdown": "Hello, **world**.",
        "cache_path": cache_path,
    }
    defaults.update(kwargs)
    draft = Draft(**defaults)  # type: ignore[arg-type]
    # Write the file so send_reply can re-parse it
    from phyrax.composer import save_draft

    save_draft(draft)
    return draft


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------


def test_render_html_calls_pandoc_with_exact_argv() -> None:
    """render_html invokes pandoc -f gfm -t html5 --no-standalone."""
    mock_result = MagicMock()
    mock_result.stdout = b"<p>Hello</p>\n"
    with patch("phyrax.sender.subprocess.run", return_value=mock_result) as mock_run:
        render_html("Hello")
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[:4] == ["pandoc", "-f", "gfm", "-t"]
    assert "html5" in args
    assert "--no-standalone" in args


def test_render_html_wraps_fragment_in_envelope() -> None:
    """render_html wraps the pandoc output in the minimal HTML envelope."""
    mock_result = MagicMock()
    mock_result.stdout = b"<p>Hello</p>\n"
    with patch("phyrax.sender.subprocess.run", return_value=mock_result):
        html = render_html("Hello")
    assert html.startswith("<html>")
    assert "<p>Hello</p>" in html
    assert html.endswith("</html>")


def test_render_html_raises_send_error_on_pandoc_failure() -> None:
    """render_html wraps CalledProcessError in SendError."""
    exc = subprocess.CalledProcessError(1, "pandoc", stderr=b"pandoc: not found")
    with (
        patch("phyrax.sender.subprocess.run", side_effect=exc),
        pytest.raises(SendError, match="pandoc failed"),
    ):
        render_html("some markdown")


# ---------------------------------------------------------------------------
# send_reply
# ---------------------------------------------------------------------------


def test_send_reply_builds_multipart_alternative(tmp_path: Path) -> None:
    """send_reply constructs multipart/alternative with text/plain and text/html."""
    draft = _make_draft(tmp_path)
    pandoc_result = MagicMock()
    pandoc_result.stdout = b"<p>Hello</p>\n"
    gmi_result = MagicMock()

    captured_input: list[bytes] = []

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[0] == "pandoc":
            return pandoc_result
        if cmd[0] == "gmi":
            captured_input.append(kwargs.get("input", b""))  # type: ignore[arg-type]
            return gmi_result
        return MagicMock()

    with patch("phyrax.sender.subprocess.run", side_effect=fake_run):
        send_reply(draft)

    assert captured_input, "gmi send was not called"
    parsed = email.message_from_bytes(captured_input[0])
    content_types = {part.get_content_type() for part in parsed.walk()}
    assert "text/plain" in content_types
    assert "text/html" in content_types


def test_send_reply_sets_required_headers(tmp_path: Path) -> None:
    """send_reply sets From, To, Subject, In-Reply-To, Message-ID."""
    draft = _make_draft(tmp_path)
    pandoc_result = MagicMock()
    pandoc_result.stdout = b"<p>body</p>\n"
    captured: list[bytes] = []

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[0] == "gmi":
            captured.append(kwargs.get("input", b""))  # type: ignore[arg-type]
        return MagicMock()

    with patch("phyrax.sender.subprocess.run", side_effect=fake_run):
        send_reply(draft)

    parsed = email.message_from_bytes(captured[0])
    assert parsed["From"] == "sender@example.com"
    assert "recipient@example.com" in parsed["To"]
    assert parsed["Subject"] == "Re: Test Subject"
    assert parsed["In-Reply-To"] == "<original@example.com>"
    assert parsed["Message-ID"] is not None


def test_send_reply_pipes_bytes_to_gmi(tmp_path: Path) -> None:
    """send_reply runs gmi send -t with message bytes on stdin."""
    draft = _make_draft(tmp_path)
    pandoc_result = MagicMock()
    pandoc_result.stdout = b"<p>x</p>\n"

    with patch("phyrax.sender.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock()
        send_reply(draft)

    gmi_calls = [c for c in mock_run.call_args_list if c[0][0][0] == "gmi"]
    assert len(gmi_calls) == 1
    gmi_call = gmi_calls[0]
    assert gmi_call[0][0] == ["gmi", "send", "-t"]
    assert isinstance(gmi_call[1].get("input"), bytes)


def test_send_reply_raises_send_error_on_gmi_failure(tmp_path: Path) -> None:
    """send_reply raises SendError with stderr when gmi exits non-zero."""
    draft = _make_draft(tmp_path)
    pandoc_result = MagicMock()
    pandoc_result.stdout = b"<p>x</p>\n"

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[0] == "pandoc":
            return pandoc_result
        raise subprocess.CalledProcessError(1, "gmi", stderr=b"auth error")

    with (
        patch("phyrax.sender.subprocess.run", side_effect=fake_run),
        pytest.raises(SendError, match="gmi send failed"),
    ):
        send_reply(draft)


def test_send_reply_cleans_up_draft_on_success(tmp_path: Path) -> None:
    """send_reply calls cleanup_draft after successful gmi dispatch."""
    draft = _make_draft(tmp_path)
    assert draft.cache_path.exists()

    pandoc_result = MagicMock()
    pandoc_result.stdout = b"<p>x</p>\n"

    with patch("phyrax.sender.subprocess.run", return_value=MagicMock()):
        send_reply(draft)

    assert not draft.cache_path.exists()


# ---------------------------------------------------------------------------
# preview_in_browser
# ---------------------------------------------------------------------------


def test_preview_in_browser_writes_file_and_opens(tmp_path: Path) -> None:
    """preview_in_browser writes HTML to a temp file and calls xdg-open."""
    with patch("phyrax.sender.subprocess.run") as mock_run:
        preview_in_browser("<html><body>test</body></html>")

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "xdg-open"
    opened_path = Path(args[1])
    assert opened_path.suffix == ".html"
