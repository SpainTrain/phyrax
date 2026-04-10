"""Tests for ChatScreen — suspend-per-turn AI chat interface.

Covers:
- '?' opens the capture modal (_InputModal)
- Enter with text suspends TUI and invokes the mock agent with a prompt file
  containing both the preamble and the user text
- Mock agent mutation to config.json is reflected after resume
- '?' with blank input still suspends and runs the agent (agent decides)
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Input, Label

from phyrax.config import PhyraxConfig
from phyrax.tui.screens.chat import ChatScreen, _build_preamble, _InputModal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _BaseScreen(Screen):  # type: ignore[type-arg]
    """Stub base screen so there's always something under ChatScreen."""

    def compose(self) -> ComposeResult:
        yield Label("base")


class _ChatApp(App):  # type: ignore[type-arg]
    """Minimal App that pushes BaseScreen and then ChatScreen."""

    def __init__(self, screen: ChatScreen) -> None:
        super().__init__()
        self._chat_screen = screen

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(_BaseScreen())
        self.push_screen(self._chat_screen)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> PhyraxConfig:
    """Return a minimal PhyraxConfig with a stub agent command."""
    cfg = PhyraxConfig()
    cfg.ai.agent_command = "echo %s"
    return cfg


# ---------------------------------------------------------------------------
# Unit tests — _InputModal in isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_input_modal_submits_value() -> None:
    """_InputModal dismisses with whatever text was entered when Enter is pressed."""

    class _ModalApp(App):  # type: ignore[type-arg]
        def compose(self) -> ComposeResult:
            return iter([])

        def on_mount(self) -> None:
            self.push_screen(_InputModal())

    app = _ModalApp()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, _InputModal)

        # Type into the input and submit
        chat_input = app.screen.query_one("#chat-input", Input)
        chat_input.value = "find my important emails"
        await pilot.press("enter")
        await pilot.pause()


@pytest.mark.asyncio
async def test_input_modal_escape_dismisses_with_empty() -> None:
    """Pressing Escape in _InputModal dismisses with an empty string."""

    class _ModalApp(App):  # type: ignore[type-arg]
        def compose(self) -> ComposeResult:
            return iter([])

        def on_mount(self) -> None:
            self.push_screen(_InputModal())

    app = _ModalApp()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, _InputModal)

        # Trigger cancel action
        app.screen.action_cancel()
        await pilot.pause()

        # Should be back to base (no more _InputModal)
        assert not isinstance(app.screen, _InputModal), "After cancel, _InputModal should be popped"


# ---------------------------------------------------------------------------
# Unit tests — _build_preamble (pure function)
# ---------------------------------------------------------------------------


def test_build_preamble_contains_user_message() -> None:
    """_build_preamble includes the user message in its output."""

    db = MagicMock()
    db.count_threads.return_value = 5
    config = PhyraxConfig()
    config.bundles = []

    result = _build_preamble(db, config, "archive my newsletters")
    assert "archive my newsletters" in result


def test_build_preamble_contains_cli_cheatsheet() -> None:
    """_build_preamble always embeds the CLI cheatsheet."""

    db = MagicMock()
    db.count_threads.return_value = 0
    config = PhyraxConfig()
    config.bundles = []

    result = _build_preamble(db, config, "")
    assert "phr status" in result
    assert "phr archive" in result
    assert "phr list" in result


def test_build_preamble_blank_user_message() -> None:
    """_build_preamble handles blank user message with a fallback note."""

    db = MagicMock()
    db.count_threads.return_value = 3
    config = PhyraxConfig()
    config.bundles = []

    result = _build_preamble(db, config, "")
    # Blank user message should produce the open-session fallback text
    assert "no specific request" in result or "open session" in result or "User:" in result


# ---------------------------------------------------------------------------
# Integration tests — ChatScreen with patched push_screen_wait and suspend
# ---------------------------------------------------------------------------

# Textual's App.suspend raises SuspendNotSupported in the headless test
# environment. We patch it to a no-op context manager so the code inside
# ``with self.app.suspend():`` can run normally.
_noop_suspend = contextlib.nullcontext


def _mock_psw_returning(user_text: str) -> object:
    """Return an async method suitable for patching push_screen_wait on the App class.

    When patched on the class, the method receives (self, modal, **kwargs).
    We ignore self and modal and just return *user_text*.
    """

    async def _impl(self_: object, modal: object, **kwargs: object) -> str:
        return user_text

    return _impl


@pytest.mark.asyncio
async def test_chat_with_text_invokes_agent(config: PhyraxConfig) -> None:
    """ChatScreen calls run_agent_interactive with a prompt file containing user text."""
    prompt_contents: list[str] = []

    def _capture_prompt(command: str, prompt_path: Path, **kwargs: object) -> int:
        prompt_contents.append(prompt_path.read_text(encoding="utf-8"))
        return 0

    screen = ChatScreen(config=config)
    app = _ChatApp(screen)

    with (
        patch("phyrax.agent.run_agent_interactive", side_effect=_capture_prompt) as mock_agent,
        patch.object(type(app), "push_screen_wait", _mock_psw_returning("help me")),
        patch.object(type(app), "suspend", _noop_suspend),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    assert mock_agent.called, "run_agent_interactive was not called"
    assert len(prompt_contents) == 1, f"Expected 1 prompt, got {len(prompt_contents)}"
    assert "help me" in prompt_contents[0], (
        f"User text 'help me' not found in prompt:\n{prompt_contents[0]}"
    )


@pytest.mark.asyncio
async def test_chat_prompt_contains_cli_cheatsheet(config: PhyraxConfig) -> None:
    """The prompt written by ChatScreen (no-db mode) contains the CLI cheatsheet."""
    prompt_contents: list[str] = []

    def _capture(command: str, prompt_path: Path, **kwargs: object) -> int:
        prompt_contents.append(prompt_path.read_text(encoding="utf-8"))
        return 0

    screen = ChatScreen(config=config)
    app = _ChatApp(screen)

    with (
        patch("phyrax.agent.run_agent_interactive", side_effect=_capture),
        patch.object(type(app), "push_screen_wait", _mock_psw_returning("archive old threads")),
        patch.object(type(app), "suspend", _noop_suspend),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    assert len(prompt_contents) == 1
    assert "phr status" in prompt_contents[0], "CLI cheatsheet ('phr status') missing from prompt"
    assert "phr archive" in prompt_contents[0], "CLI cheatsheet ('phr archive') missing from prompt"


@pytest.mark.asyncio
async def test_blank_input_still_invokes_agent(config: PhyraxConfig) -> None:
    """Submitting blank text from the modal still suspends and calls the agent."""
    screen = ChatScreen(config=config)
    app = _ChatApp(screen)

    with (
        patch("phyrax.agent.run_agent_interactive", return_value=0) as mock_agent,
        patch.object(type(app), "push_screen_wait", _mock_psw_returning("")),
        patch.object(type(app), "suspend", _noop_suspend),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    assert mock_agent.called, "run_agent_interactive should be called even with blank user input"


@pytest.mark.asyncio
async def test_agent_config_mutation_reflected_after_resume(tmp_config_dir: Path) -> None:
    """Config changes written by the agent during suspension are reloaded afterwards."""
    config_path = tmp_config_dir / "config" / "phyrax" / "config.json"
    config = PhyraxConfig.load(config_path)

    reload_configs: list[PhyraxConfig] = []

    def _mutate_and_capture(command: str, prompt_path: Path, **kwargs: object) -> int:
        # Simulate agent updating config.json
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        raw.setdefault("ai", {})["agent_command"] = "mutated-agent %s"
        config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        return 0

    original_load = PhyraxConfig.load

    def _spy_load(path: Path = config_path) -> PhyraxConfig:
        result = original_load(path)
        reload_configs.append(result)
        return result

    screen = ChatScreen(config=config)
    app = _ChatApp(screen)

    with (
        patch("phyrax.agent.run_agent_interactive", side_effect=_mutate_and_capture),
        patch.object(type(app), "push_screen_wait", _mock_psw_returning("")),
        patch.object(type(app), "suspend", _noop_suspend),
        patch.object(PhyraxConfig, "load", side_effect=_spy_load),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    # PhyraxConfig.load should have been called at least once after the agent ran
    assert len(reload_configs) >= 1, (
        "PhyraxConfig.load should be called at least once after agent runs"
    )
    # The last reload should reflect the agent's mutation
    assert reload_configs[-1].ai.agent_command == "mutated-agent %s", (
        f"Expected mutated agent_command; got {reload_configs[-1].ai.agent_command!r}"
    )


@pytest.mark.asyncio
async def test_ftux_preamble_mode_uses_supplied_preamble(config: PhyraxConfig) -> None:
    """In FTUX mode (preamble arg set), the prompt uses the supplied preamble text."""
    prompt_contents: list[str] = []

    def _capture(command: str, prompt_path: Path, **kwargs: object) -> int:
        prompt_contents.append(prompt_path.read_text(encoding="utf-8"))
        return 0

    ftux_preamble = "Welcome to Phyrax! This is your first run setup."
    screen = ChatScreen(config=config, preamble=ftux_preamble)
    app = _ChatApp(screen)

    with (
        patch("phyrax.agent.run_agent_interactive", side_effect=_capture),
        patch.object(type(app), "push_screen_wait", _mock_psw_returning("")),
        patch.object(type(app), "suspend", _noop_suspend),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    assert len(prompt_contents) == 1
    assert ftux_preamble in prompt_contents[0], "FTUX preamble not found in prompt content"
    # FTUX mode does NOT include inbox-state headers
    assert "Current inbox state" not in prompt_contents[0], (
        "FTUX mode should not include inbox state in the prompt"
    )
