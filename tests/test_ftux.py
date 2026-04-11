"""Tests for phyrax.ftux.wizard — bootstrap wizard and post-bootstrap handoff.

Coverage:
- WizardScreen: binary present on PATH → dismisses with correct _WizardResult
- WizardScreen: missing binary → warning shown, user can bypass via btn-proceed
- run_bootstrap_wizard: returns AIConfig from wizard result
- run_post_bootstrap_handoff: fires only when is_first_run; pushes ChatScreen
- FIRST_RUN_PREAMBLE: mentions key phr concepts (phr compose, identity, bundles, docs/actions/)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from textual import work
from textual.app import App, ComposeResult

from phyrax.config import AIConfig
from phyrax.ftux.wizard import (
    FIRST_RUN_PREAMBLE,
    WizardScreen,
    _WizardResult,
    run_bootstrap_wizard,
    run_post_bootstrap_handoff,
)

# ---------------------------------------------------------------------------
# Helper: host app that pushes WizardScreen and captures the result
# ---------------------------------------------------------------------------


class _HostApp(App[_WizardResult | None]):
    """Minimal host app used in tests to push WizardScreen as a modal."""

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self._run_wizard()

    @work
    async def _run_wizard(self) -> None:
        # push_screen_wait requires a worker context.
        result = await self.push_screen_wait(WizardScreen())
        self.exit(result)


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
# WizardScreen: binary present on PATH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wizard_binary_found_returns_result_with_command() -> None:
    """Selecting a preset whose binary is on PATH dismisses with the correct command."""
    app = _HostApp()

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
async def test_wizard_binary_found_no_proceed_anyway() -> None:
    """When binary is found, _proceed_anyway must be False."""
    app = _HostApp()

    with patch("phyrax.ftux.wizard.shutil.which", return_value="/usr/bin/claude"):
        async with app.run_test() as pilot:
            await pilot.click("#btn-select")
            await pilot.pause()

    result = app.return_value
    assert result is not None
    assert result._proceed_anyway is False


@pytest.mark.asyncio
async def test_wizard_gemini_preset_command() -> None:
    """Selecting the Gemini CLI preset returns the correct command template."""
    app = _HostApp()

    with patch("phyrax.ftux.wizard.shutil.which", return_value="/usr/local/bin/gemini"):
        async with app.run_test() as pilot:
            # Wait for the worker to push WizardScreen.
            await pilot.pause()
            # Query from the active screen (the WizardScreen modal), not the default.
            list_view = pilot.app.screen.query_one("#preset-list")
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
# WizardScreen: binary missing from PATH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wizard_missing_binary_shows_warning() -> None:
    """When binary is not on PATH, clicking Select reveals the warning label."""
    app = _HostApp()

    with patch("phyrax.ftux.wizard.shutil.which", return_value=None):
        async with app.run_test() as pilot:
            # Wait for worker to push WizardScreen.
            await pilot.pause()
            await pilot.click("#btn-select")
            await pilot.pause()
            # Query from the active screen (the WizardScreen modal).
            warning = pilot.app.screen.query_one("#warning-label")
            assert warning.display is True
            # Dismiss to avoid hanging.
            await pilot.click("#btn-proceed")
            await pilot.pause()


@pytest.mark.asyncio
async def test_wizard_missing_binary_proceed_anyway_exits_with_command() -> None:
    """Clicking 'Proceed anyway' dismisses the wizard even when binary is missing."""
    app = _HostApp()

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
    app = _HostApp()

    with patch("phyrax.ftux.wizard.shutil.which", return_value=None):
        async with app.run_test() as pilot:
            # Wait for worker to push WizardScreen.
            await pilot.pause()
            await pilot.click("#btn-select")
            await pilot.pause()
            # Query from the active screen (the WizardScreen modal).
            warning = pilot.app.screen.query_one("#warning-label")
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
    # _WizardHostApp is a local class inside run_bootstrap_wizard, so we can't
    # patch it directly.  Instead, patch App.run on the base class so the
    # internal _WizardHostApp().run() returns a controlled result.
    mock_result = _WizardResult(command="myai --prompt %s")

    with patch("phyrax.ftux.wizard.App.run", return_value=mock_result):
        result = run_bootstrap_wizard()

    assert isinstance(result, AIConfig)
    assert result.agent_command == "myai --prompt %s"


def test_run_bootstrap_wizard_dismissed_returns_default_ai_config() -> None:
    """If user dismisses the wizard (result=None), return default AIConfig."""
    with patch("phyrax.ftux.wizard.App.run", return_value=None):
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
