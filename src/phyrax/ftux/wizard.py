"""FTUX bootstrap wizard and post-bootstrap ChatScreen handoff.

The wizard only asks for the AI CLI command (validates binary on PATH).
Everything else — identity, aliases, bundles, task action — is configured
by the AI agent in ChatScreen after the bootstrap completes.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView

from phyrax.config import AIConfig

# ---------------------------------------------------------------------------
# First-run preamble for ChatScreen handoff
# ---------------------------------------------------------------------------

FIRST_RUN_PREAMBLE: str = """\
Welcome to Phyrax! This is your first run. I'll help you finish setting up.

We need to configure a few things:

1. **Identity** — Set your primary email address and any aliases you send from.
   Run `phr compose` to draft your first email once identity is configured.

2. **Bundles** — Define at least one bundle to organise your inbox by topic,
   sender, or label. Bundles are the core of Phyrax's triage workflow.
   Use `phr list --bundle=<name>` to preview threads in each bundle.

3. **Task action** — Copy a task template from docs/actions/ into your personal
   actions directory so the `t` key can extract tasks from email threads.

Let's start with your identity. What email address do you send from?
"""

# ---------------------------------------------------------------------------
# Preset definitions
# ---------------------------------------------------------------------------

_PRESETS: list[tuple[str, str]] = [
    ("Claude Code", "claude -p %s"),
    ("Gemini CLI", "gemini --input %s"),
    ("Goose", "goose run --prompt-file %s"),
    ("OpenCode", "opencode --file %s"),
    ("Custom", ""),
]

_CUSTOM_INDEX = len(_PRESETS) - 1


# ---------------------------------------------------------------------------
# Internal result container
# ---------------------------------------------------------------------------


@dataclass
class _WizardResult:
    command: str
    _proceed_anyway: bool = field(default=False)


# ---------------------------------------------------------------------------
# Wizard screen — extends ModalScreen so it can be pushed onto an existing app
# ---------------------------------------------------------------------------


class WizardScreen(ModalScreen[_WizardResult | None]):
    """Modal screen that collects the AI CLI command during first-run setup."""

    CSS = """
    WizardScreen {
        align: center middle;
    }
    Vertical {
        width: 70;
        height: auto;
        padding: 1 2;
        border: solid $primary;
        background: $surface;
    }
    #title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #subtitle {
        text-align: center;
        margin-bottom: 1;
        color: $text-muted;
    }
    #preset-list {
        height: auto;
        margin-bottom: 1;
    }
    #custom-input {
        display: none;
        margin-bottom: 1;
    }
    #warning-label {
        display: none;
        color: $warning;
        text-align: center;
        margin-bottom: 1;
    }
    #btn-row {
        height: auto;
        layout: horizontal;
        align: center middle;
    }
    Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Phyrax — First-Run Setup", id="title")
            yield Label("Choose your AI CLI agent:", id="subtitle")
            with ListView(id="preset-list"):
                for name, _ in _PRESETS:
                    yield ListItem(Label(name))
            yield Input(placeholder="e.g. myai --prompt %s", id="custom-input")
            yield Label("Binary not found on PATH", id="warning-label")
            with Vertical(id="btn-row"):
                yield Button("Select", variant="primary", id="btn-select")
                yield Button("Proceed anyway", variant="warning", id="btn-proceed")
                yield Button("Re-select", variant="default", id="btn-reselect")

    def on_mount(self) -> None:
        self._selected_index: int = 0
        self._show_warning = False
        self._update_button_visibility()

    def _update_button_visibility(self) -> None:
        warning = self.query_one("#warning-label", Label)
        btn_proceed = self.query_one("#btn-proceed", Button)
        btn_reselect = self.query_one("#btn-reselect", Button)
        if self._show_warning:
            warning.display = True
            btn_proceed.display = True
            btn_reselect.display = True
        else:
            warning.display = False
            btn_proceed.display = False
            btn_reselect.display = False

    def _get_current_command(self) -> str:
        if self._selected_index == _CUSTOM_INDEX:
            return self.query_one("#custom-input", Input).value.strip()
        return _PRESETS[self._selected_index][1]

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self._selected_index = event.list_view.index or 0
        custom_input = self.query_one("#custom-input", Input)
        if self._selected_index == _CUSTOM_INDEX:
            custom_input.display = True
            custom_input.focus()
        else:
            custom_input.display = False
        # Reset warning state when making a new selection
        self._show_warning = False
        self._update_button_visibility()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-select":
            self._attempt_select(proceed_anyway=False)
        elif button_id == "btn-proceed":
            command = self._get_current_command()
            self.dismiss(_WizardResult(command=command, _proceed_anyway=True))
        elif button_id == "btn-reselect":
            self._show_warning = False
            self._update_button_visibility()
            self.query_one("#preset-list", ListView).focus()

    def _attempt_select(self, *, proceed_anyway: bool) -> None:
        command = self._get_current_command()
        if not command:
            # No command entered yet — do nothing
            return

        token = command.split()[0]
        if shutil.which(token) is not None:
            # Binary found — proceed immediately
            self.dismiss(_WizardResult(command=command))
        else:
            # Binary not found — show warning and offer bypass/reselect
            self._show_warning = True
            self._update_button_visibility()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        """Allow pressing Enter in the custom input to trigger selection."""
        self._attempt_select(proceed_anyway=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_bootstrap_wizard() -> AIConfig:
    """Present AI CLI selection screen and return a populated AIConfig.

    Presets: Claude Code, Gemini CLI, Goose, OpenCode, Custom.
    Validates binary with shutil.which(); warns but allows bypass if not found.

    Note: This function creates a standalone App to host the WizardScreen and
    blocks until it exits. It must NOT be called from inside a running Textual
    event loop (e.g. from on_mount). Use ``push_screen_wait(WizardScreen())``
    instead when inside an async context.
    """

    class _WizardHostApp(App[_WizardResult | None]):
        def on_mount(self) -> None:
            self.push_screen(WizardScreen(), callback=self.exit)

    host = _WizardHostApp()
    result = host.run()
    if result is None:
        # User dismissed the wizard without selecting — use default
        return AIConfig()
    return AIConfig(agent_command=result.command)


def run_post_bootstrap_handoff(app: App[Any]) -> None:
    """Push ChatScreen with a seeded preamble for first-run configuration.

    The preamble instructs the agent to collect identity.primary, aliases,
    at least one bundle, and copy a task template from docs/actions/ to ACTIONS_DIR.
    Only fires when config.is_first_run was True at app mount.
    """
    from phyrax.tui.screens.chat import ChatScreen

    app.push_screen(ChatScreen(preamble=FIRST_RUN_PREAMBLE))
