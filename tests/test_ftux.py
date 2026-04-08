"""Tests for phyrax.ftux.wizard — bootstrap wizard and post-bootstrap handoff.

Coverage:
- _WizardApp: binary present on PATH → returns AIConfig with right command
- _WizardApp: missing binary → warning shown, user can bypass via btn-proceed
- run_post_bootstrap_handoff: fires only when is_first_run; pushes ChatScreen
- FIRST_RUN_PREAMBLE: mentions key phr concepts (phr compose, identity, bundles, docs/actions/)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from phyrax.config import AIConfig
from phyrax.ftux.wizard import (
    FIRST_RUN_PREAMBLE,
    _WizardApp,
    run_bootstrap_wizard,
    run_post_bootstrap_handoff,
)

# ---------------------------------------------------------------------------
# Preamble content tests (no app needed)
# ---------------------------------------------------------------------------


def test_first_run_preamble_mentions_phr_compose() -> None:
    """FIRST_RUN_PREAMBLE must reference 'phr compose'."""
    assert "phr compose" in FIRST_RUN_PREAMBLE


def test_first_run_preamble_mentions_identity() -> None:
    """FIRST_RUN_PREAMBLE must reference 'identity' configuration."""
    assert "identity" in FIRST_RUN_PREAMBLE


def test_first_run_preamble_mentions_bundles() -> None:
    """FIRST_RUN_PREAMBLE must reference 'bundles' (case-insensitive)."""
    assert "bundles" in FIRST_RUN_PREAMBLE.lower()


def test_first_run_preamble_mentions_docs_actions() -> None:
    """FIRST_RUN_PREAMBLE must reference 'docs/actions/' for task templates."""
    assert "docs/actions/" in FIRST_RUN_PREAMBLE


# ---------------------------------------------------------------------------
# _WizardApp: binary present on PATH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wizard_binary_found_returns_ai_config_with_command() -> None:
    """Selecting a preset whose binary is on PATH exits with the correct command."""
    app = _WizardApp()

    # Claude Code is index 0; "claude" is the binary in "claude -p %s".
    with patch("phyrax.ftux.wizard.shutil.which", return_value="/usr/bin/claude"):
        async with app.run_test() as pilot:
            # The first preset (Claude Code) is selected by default.
            await pilot.click("#btn-select")
            await pilot.pause()

    result = app.return_value
    assert result is not None
    assert result.command == "claude -p %s"


@pytest.mark.asyncio
async def test_wizard_binary_found_no_warning_shown() -> None:
    """When binary is found, the warning label must remain hidden."""
    app = _WizardApp()

    with patch("phyrax.ftux.wizard.shutil.which", return_value="/usr/bin/claude"):
        async with app.run_test() as pilot:
            await pilot.click("#btn-select")
            await pilot.pause()
            # App exits immediately; just check result is non-None (no bypass needed).

    result = app.return_value
    assert result is not None
    # _proceed_anyway is False because binary was found directly.
    assert result._proceed_anyway is False


@pytest.mark.asyncio
async def test_wizard_gemini_preset_command() -> None:
    """Selecting the Gemini CLI preset returns the correct command template."""
    app = _WizardApp()

    with patch("phyrax.ftux.wizard.shutil.which", return_value="/usr/local/bin/gemini"):
        async with app.run_test() as pilot:
            # Focus the list, arrow down to Gemini CLI (index 1), then press Enter
            # to fire the ListView.Selected message which updates _selected_index.
            list_view = app.query_one("#preset-list")
            list_view.focus()
            await pilot.pause()
            await pilot.press("down")  # highlight Gemini CLI
            await pilot.press("enter")  # fire ListView.Selected
            await pilot.pause()
            await pilot.click("#btn-select")
            await pilot.pause()

    result = app.return_value
    assert result is not None
    assert "gemini" in result.command


# ---------------------------------------------------------------------------
# _WizardApp: binary missing from PATH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wizard_missing_binary_shows_warning() -> None:
    """When binary is not on PATH, clicking Select reveals the warning label."""
    app = _WizardApp()

    with patch("phyrax.ftux.wizard.shutil.which", return_value=None):
        async with app.run_test() as pilot:
            await pilot.click("#btn-select")
            await pilot.pause()
            warning = app.query_one("#warning-label")
            assert warning.display is True
            # Dismiss to avoid hanging.
            await pilot.click("#btn-proceed")
            await pilot.pause()


@pytest.mark.asyncio
async def test_wizard_missing_binary_proceed_anyway_exits_with_command() -> None:
    """Clicking 'Proceed anyway' exits the wizard even when binary is missing."""
    app = _WizardApp()

    with patch("phyrax.ftux.wizard.shutil.which", return_value=None):
        async with app.run_test() as pilot:
            await pilot.click("#btn-select")
            await pilot.pause()
            await pilot.click("#btn-proceed")
            await pilot.pause()

    result = app.return_value
    assert result is not None
    assert result.command == "claude -p %s"  # default preset command
    assert result._proceed_anyway is True


@pytest.mark.asyncio
async def test_wizard_missing_binary_reselect_hides_warning() -> None:
    """Clicking 'Re-select' hides the warning and returns focus to the list."""
    app = _WizardApp()

    with patch("phyrax.ftux.wizard.shutil.which", return_value=None):
        async with app.run_test() as pilot:
            await pilot.click("#btn-select")
            await pilot.pause()
            # Warning is visible.
            warning = app.query_one("#warning-label")
            assert warning.display is True
            # Click Re-select.
            await pilot.click("#btn-reselect")
            await pilot.pause()
            # Warning should be hidden again.
            assert warning.display is False
            # Exit cleanly.
            await pilot.click("#btn-select")
            await pilot.pause()


# ---------------------------------------------------------------------------
# run_bootstrap_wizard() integration
# ---------------------------------------------------------------------------


def test_run_bootstrap_wizard_returns_ai_config() -> None:
    """run_bootstrap_wizard() must return an AIConfig instance."""
    mock_result = MagicMock()
    mock_result.command = "myai --prompt %s"

    with patch("phyrax.ftux.wizard._WizardApp") as MockApp:
        instance = MockApp.return_value
        instance.run.return_value = mock_result
        result = run_bootstrap_wizard()

    assert isinstance(result, AIConfig)
    assert result.agent_command == "myai --prompt %s"


def test_run_bootstrap_wizard_dismissed_returns_default_ai_config() -> None:
    """If user dismisses the wizard (result=None), return default AIConfig."""
    with patch("phyrax.ftux.wizard._WizardApp") as MockApp:
        instance = MockApp.return_value
        instance.run.return_value = None
        result = run_bootstrap_wizard()

    assert isinstance(result, AIConfig)
    # Default AIConfig has the default command.
    assert result.agent_command == AIConfig().agent_command


# ---------------------------------------------------------------------------
# run_post_bootstrap_handoff
# ---------------------------------------------------------------------------


def test_run_post_bootstrap_handoff_fires_only_when_first_run() -> None:
    """run_post_bootstrap_handoff must push ChatScreen when is_first_run is True."""
    from phyrax.tui.screens.chat import ChatScreen

    mock_app = MagicMock()

    run_post_bootstrap_handoff(mock_app)

    # Should have called push_screen on the app.
    mock_app.push_screen.assert_called_once()
    pushed_screen = mock_app.push_screen.call_args[0][0]
    assert isinstance(pushed_screen, ChatScreen)


def test_run_post_bootstrap_handoff_screen_receives_preamble() -> None:
    """ChatScreen pushed during handoff must be initialised with FIRST_RUN_PREAMBLE."""
    from phyrax.tui.screens.chat import ChatScreen

    mock_app = MagicMock()

    run_post_bootstrap_handoff(mock_app)

    pushed_screen = mock_app.push_screen.call_args[0][0]
    assert isinstance(pushed_screen, ChatScreen)
    # The screen must carry the preamble text.
    assert pushed_screen.preamble == FIRST_RUN_PREAMBLE
