"""Tests for phyrax.actions.engine — list_actions and execute_action."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from phyrax.actions.engine import ActionTemplate, execute_action, list_actions
from phyrax.config import PhyraxConfig
from phyrax.exceptions import AgentError
from phyrax.models import MessageDetail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_action(
    directory: Path,
    filename: str,
    name: str,
    description: str = "A test action",
    **extra: object,
) -> Path:
    """Write a valid action template file and return its path."""
    fm_lines = [f"name: {name}", f"description: {description}"]
    for k, v in extra.items():
        fm_lines.append(f"{k}: {str(v).lower()}")
    content = "---\n" + "\n".join(fm_lines) + "\n---\n\nDo the thing.\n"
    path = directory / filename
    path.write_text(content)
    return path


def _make_message(**overrides: object) -> MessageDetail:
    """Return a MessageDetail with sensible defaults, allowing field overrides."""
    defaults: dict[str, object] = dict(
        message_id="<test@fixture>",
        thread_id="t1",
        from_="a@b.com",
        to=["me@example.com"],
        cc=[],
        date=1_735_732_800,
        subject="Test",
        headers={},
        body_plain="Hello",
        body_html=None,
        tags=frozenset(),
        attachments=[],
    )
    defaults.update(overrides)
    return MessageDetail(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# list_actions — empty directory
# ---------------------------------------------------------------------------


def test_list_actions_empty_directory_returns_empty_list(tmp_path: Path) -> None:
    """list_actions returns [] when the directory exists but contains no .md files."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()

    result = list_actions(actions_dir)

    assert result == []


def test_list_actions_nonexistent_directory_returns_empty_list(tmp_path: Path) -> None:
    """list_actions returns [] when the directory does not exist."""
    missing_dir = tmp_path / "no_such_dir"

    result = list_actions(missing_dir)

    assert result == []


# ---------------------------------------------------------------------------
# list_actions — single valid file
# ---------------------------------------------------------------------------


def test_list_actions_one_valid_file_returns_one_template(tmp_path: Path) -> None:
    """list_actions returns a list with exactly one ActionTemplate for a single valid file."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    _write_action(actions_dir, "alpha.md", name="Alpha Action", description="Does alpha things")

    result = list_actions(actions_dir)

    assert len(result) == 1
    assert isinstance(result[0], ActionTemplate)


def test_list_actions_one_valid_file_fields_match_frontmatter(tmp_path: Path) -> None:
    """Parsed ActionTemplate fields match the frontmatter in the file."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    source = _write_action(
        actions_dir,
        "alpha.md",
        name="Alpha Action",
        description="Does alpha things",
        require_full_context="true",
        allow_attachments="false",
    )

    result = list_actions(actions_dir)

    assert len(result) == 1
    tpl = result[0]
    assert tpl.name == "Alpha Action"
    assert tpl.description == "Does alpha things"
    assert tpl.require_full_context is True
    assert tpl.allow_attachments is False
    assert tpl.source_path == source
    assert "Do the thing." in tpl.prompt_body


# ---------------------------------------------------------------------------
# list_actions — three valid files, sorted alphabetically
# ---------------------------------------------------------------------------


def test_list_actions_three_files_returns_three_templates(tmp_path: Path) -> None:
    """list_actions returns exactly 3 ActionTemplates for 3 valid files."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    _write_action(actions_dir, "charlie.md", name="Charlie")
    _write_action(actions_dir, "alpha.md", name="Alpha")
    _write_action(actions_dir, "bravo.md", name="Bravo")

    result = list_actions(actions_dir)

    assert len(result) == 3


def test_list_actions_three_files_sorted_alphabetically_by_name(tmp_path: Path) -> None:
    """list_actions returns templates sorted alphabetically by name."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    _write_action(actions_dir, "charlie.md", name="Charlie")
    _write_action(actions_dir, "alpha.md", name="Alpha")
    _write_action(actions_dir, "bravo.md", name="Bravo")

    result = list_actions(actions_dir)

    assert [t.name for t in result] == ["Alpha", "Bravo", "Charlie"]


# ---------------------------------------------------------------------------
# list_actions — optional field defaults
# ---------------------------------------------------------------------------


def test_list_actions_defaults_require_full_context_to_false(tmp_path: Path) -> None:
    """require_full_context defaults to False when omitted from frontmatter."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    _write_action(actions_dir, "minimal.md", name="Minimal", description="No optional fields")

    result = list_actions(actions_dir)

    assert len(result) == 1
    assert result[0].require_full_context is False


def test_list_actions_defaults_allow_attachments_to_false(tmp_path: Path) -> None:
    """allow_attachments defaults to False when omitted from frontmatter."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    _write_action(actions_dir, "minimal.md", name="Minimal", description="No optional fields")

    result = list_actions(actions_dir)

    assert len(result) == 1
    assert result[0].allow_attachments is False


# ---------------------------------------------------------------------------
# list_actions — malformed frontmatter is skipped with a warning
# ---------------------------------------------------------------------------


def test_list_actions_missing_name_key_returns_empty_list(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A file missing the required 'name' key is skipped and a warning is logged."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    bad_file = actions_dir / "bad.md"
    bad_file.write_text("---\ndescription: No name here\n---\n\nBody.\n")

    with caplog.at_level(logging.WARNING, logger="phyrax"):
        result = list_actions(actions_dir)

    assert result == []
    assert any("missing required frontmatter key" in rec.message for rec in caplog.records)


def test_list_actions_missing_description_key_returns_empty_list(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A file missing the required 'description' key is skipped with a warning."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    bad_file = actions_dir / "bad.md"
    bad_file.write_text("---\nname: No Description\n---\n\nBody.\n")

    with caplog.at_level(logging.WARNING, logger="phyrax"):
        result = list_actions(actions_dir)

    assert result == []
    assert any("missing required frontmatter key" in rec.message for rec in caplog.records)


def test_list_actions_no_frontmatter_skipped_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A file with no frontmatter delimiter is skipped and a warning is logged."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    bad_file = actions_dir / "plain.md"
    bad_file.write_text("Just plain markdown, no frontmatter.\n")

    with caplog.at_level(logging.WARNING, logger="phyrax"):
        result = list_actions(actions_dir)

    assert result == []
    assert len(caplog.records) >= 1


def test_list_actions_malformed_file_does_not_prevent_valid_files(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A malformed file is skipped; valid files in the same directory are still returned."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    bad_file = actions_dir / "bad.md"
    bad_file.write_text("---\ndescription: No name\n---\n\nBody.\n")
    _write_action(actions_dir, "good.md", name="Good Action")

    with caplog.at_level(logging.WARNING, logger="phyrax"):
        result = list_actions(actions_dir)

    assert len(result) == 1
    assert result[0].name == "Good Action"


# ---------------------------------------------------------------------------
# execute_action — require_full_context and allow_attachments passed to compile_prompt
# ---------------------------------------------------------------------------


def test_execute_action_passes_require_full_context_to_compile_prompt(
    tmp_path: Path,
) -> None:
    """execute_action passes require_full_context=True from the template to compile_prompt."""
    template = ActionTemplate(
        name="Test",
        description="T",
        prompt_body="Do it.",
        source_path=tmp_path / "test.md",
        require_full_context=True,
        allow_attachments=False,
    )
    msg = _make_message()
    config = PhyraxConfig()

    fd, tmp_prompt = tempfile.mkstemp()
    os.close(fd)
    tmp_prompt_path = Path(tmp_prompt)

    try:
        with patch(
            "phyrax.actions.engine._agent.compile_prompt",
            return_value=tmp_prompt_path,
        ) as mock_compile, patch(
            "phyrax.actions.engine._agent.run_agent_interactive",
            return_value=0,
        ):
            execute_action(template, msg, config)

        _call_kwargs = mock_compile.call_args
        assert _call_kwargs.kwargs.get("require_full_context") is True
    finally:
        tmp_prompt_path.unlink(missing_ok=True)


def test_execute_action_passes_allow_attachments_to_compile_prompt(
    tmp_path: Path,
) -> None:
    """execute_action passes allow_attachments=True from the template to compile_prompt."""
    template = ActionTemplate(
        name="Test",
        description="T",
        prompt_body="Do it.",
        source_path=tmp_path / "test.md",
        require_full_context=False,
        allow_attachments=True,
    )
    msg = _make_message()
    config = PhyraxConfig()

    fd, tmp_prompt = tempfile.mkstemp()
    os.close(fd)
    tmp_prompt_path = Path(tmp_prompt)

    try:
        with patch(
            "phyrax.actions.engine._agent.compile_prompt",
            return_value=tmp_prompt_path,
        ) as mock_compile, patch(
            "phyrax.actions.engine._agent.run_agent_interactive",
            return_value=0,
        ):
            execute_action(template, msg, config)

        _call_kwargs = mock_compile.call_args
        assert _call_kwargs.kwargs.get("allow_attachments") is True
    finally:
        tmp_prompt_path.unlink(missing_ok=True)


def test_execute_action_passes_prompt_body_to_compile_prompt(
    tmp_path: Path,
) -> None:
    """execute_action passes the template's prompt_body as the first positional arg."""
    template = ActionTemplate(
        name="Test",
        description="T",
        prompt_body="My custom prompt body.",
        source_path=tmp_path / "test.md",
        require_full_context=False,
        allow_attachments=False,
    )
    msg = _make_message()
    config = PhyraxConfig()

    fd, tmp_prompt = tempfile.mkstemp()
    os.close(fd)
    tmp_prompt_path = Path(tmp_prompt)

    try:
        with patch(
            "phyrax.actions.engine._agent.compile_prompt",
            return_value=tmp_prompt_path,
        ) as mock_compile, patch(
            "phyrax.actions.engine._agent.run_agent_interactive",
            return_value=0,
        ):
            execute_action(template, msg, config)

        assert mock_compile.call_args.args[0] == "My custom prompt body."
    finally:
        tmp_prompt_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# execute_action — returns the agent's exit code
# ---------------------------------------------------------------------------


def test_execute_action_returns_exit_code_zero(tmp_path: Path) -> None:
    """execute_action returns 0 when run_agent_interactive returns 0."""
    template = ActionTemplate(
        name="Test",
        description="T",
        prompt_body="Do it.",
        source_path=tmp_path / "test.md",
        require_full_context=False,
        allow_attachments=False,
    )
    msg = _make_message()
    config = PhyraxConfig()

    fd, tmp_prompt = tempfile.mkstemp()
    os.close(fd)
    tmp_prompt_path = Path(tmp_prompt)

    try:
        with patch(
            "phyrax.actions.engine._agent.compile_prompt",
            return_value=tmp_prompt_path,
        ), patch(
            "phyrax.actions.engine._agent.run_agent_interactive",
            return_value=0,
        ):
            result = execute_action(template, msg, config)
    finally:
        tmp_prompt_path.unlink(missing_ok=True)

    assert result == 0


def test_execute_action_returns_agent_exit_code_nonzero_not_raised(
    tmp_path: Path,
) -> None:
    """execute_action propagates a nonzero exit code from run_agent_interactive."""
    template = ActionTemplate(
        name="Test",
        description="T",
        prompt_body="Do it.",
        source_path=tmp_path / "test.md",
        require_full_context=False,
        allow_attachments=False,
    )
    msg = _make_message()
    config = PhyraxConfig()

    fd, tmp_prompt = tempfile.mkstemp()
    os.close(fd)
    tmp_prompt_path = Path(tmp_prompt)

    try:
        with patch(
            "phyrax.actions.engine._agent.compile_prompt",
            return_value=tmp_prompt_path,
        ), patch(
            "phyrax.actions.engine._agent.run_agent_interactive",
            return_value=2,
        ):
            result = execute_action(template, msg, config)
    finally:
        tmp_prompt_path.unlink(missing_ok=True)

    assert result == 2


# ---------------------------------------------------------------------------
# execute_action — temp file cleaned up on failure
# ---------------------------------------------------------------------------


def test_execute_action_cleans_up_temp_file_on_agent_error(
    tmp_path: Path,
) -> None:
    """execute_action deletes the temp prompt file even when run_agent_interactive raises."""
    template = ActionTemplate(
        name="Test",
        description="T",
        prompt_body="Do it.",
        source_path=tmp_path / "test.md",
        require_full_context=False,
        allow_attachments=False,
    )
    msg = _make_message()
    config = PhyraxConfig()

    # Create a real temp file; capture its path to check after the call.
    fd, tmp_prompt = tempfile.mkstemp()
    os.close(fd)
    tmp_prompt_path = Path(tmp_prompt)
    assert tmp_prompt_path.exists(), "Precondition: temp file must exist before the call"

    with patch(
        "phyrax.actions.engine._agent.compile_prompt",
        return_value=tmp_prompt_path,
    ), patch(
        "phyrax.actions.engine._agent.run_agent_interactive",
        side_effect=AgentError("agent died"),
    ), pytest.raises(AgentError):
        execute_action(template, msg, config)

    assert not tmp_prompt_path.exists(), "Temp prompt file must be deleted after AgentError"


def test_execute_action_cleans_up_temp_file_on_success(
    tmp_path: Path,
) -> None:
    """execute_action deletes the temp prompt file on successful completion."""
    template = ActionTemplate(
        name="Test",
        description="T",
        prompt_body="Do it.",
        source_path=tmp_path / "test.md",
        require_full_context=False,
        allow_attachments=False,
    )
    msg = _make_message()
    config = PhyraxConfig()

    fd, tmp_prompt = tempfile.mkstemp()
    os.close(fd)
    tmp_prompt_path = Path(tmp_prompt)

    with patch(
        "phyrax.actions.engine._agent.compile_prompt",
        return_value=tmp_prompt_path,
    ), patch(
        "phyrax.actions.engine._agent.run_agent_interactive",
        return_value=0,
    ):
        execute_action(template, msg, config)

    assert not tmp_prompt_path.exists(), "Temp prompt file must be deleted after successful run"
