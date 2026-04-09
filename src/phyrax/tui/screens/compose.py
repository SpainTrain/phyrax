"""ComposeModal — reply intent capture.

Pushed by 'r' from InboxScreen or ThreadViewScreen. Always anchored to the
newest message in the thread. Captures AI instructions and a 'full thread
context' toggle, then hands off to the composer pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, Label

from phyrax.config import PhyraxConfig
from phyrax.models import MessageDetail


@dataclass
class ComposeIntent:
    """Result from ComposeModal — the user's reply intent."""

    instructions: str  # AI instructions (empty = manual draft)
    require_full_context: bool  # Whether to include full thread context
    from_alias: str  # The alias to send from
    in_reply_to: MessageDetail  # The message being replied to


def pick_alias(message: MessageDetail, config: PhyraxConfig) -> str:
    """Choose the sending alias based on the To header of the message.

    If any configured alias matches one of the message's To addresses
    (case-insensitive), that alias is returned. Otherwise, falls back to
    config.identity.primary.
    """
    to_lower = {addr.lower() for addr in message.to}
    for alias in config.identity.aliases:
        if alias.lower() in to_lower:
            return alias
    return config.identity.primary


class ComposeModal(ModalScreen):  # type: ignore[type-arg]  # Textual ModalScreen is generic at runtime
    """Modal for capturing reply intent before AI drafting."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+j", "submit", "Submit", show=False),
    ]

    CSS = """
    ComposeModal {
        align: center middle;
    }
    #compose-panel {
        width: 70;
        height: auto;
        padding: 1 2;
        border: solid $primary;
        background: $surface;
    }
    #header-label {
        text-style: bold;
        margin-bottom: 1;
    }
    #from-label {
        color: $text-muted;
        margin-bottom: 1;
    }
    #instructions-input {
        margin-bottom: 1;
    }
    """

    def __init__(self, message: MessageDetail, config: PhyraxConfig) -> None:
        super().__init__()
        self._message = message
        self._config = config
        self._alias = pick_alias(message, config)

    def compose(self) -> ComposeResult:
        with Vertical(id="compose-panel"):
            yield Label(f"Replying to: {self._message.subject}", id="header-label")
            yield Label(f"From (alias): {self._alias}", id="from-label")
            yield Input(
                placeholder="AI instructions (blank = manual draft)",
                id="instructions-input",
            )
            yield Checkbox("Use full thread context", value=False, id="full-context")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in the instructions input field."""
        self.action_submit()

    def action_submit(self) -> None:
        """Build a ComposeIntent from current form state and dismiss."""
        instructions_input = self.query_one("#instructions-input", Input)
        full_context_cb = self.query_one("#full-context", Checkbox)
        intent = ComposeIntent(
            instructions=instructions_input.value.strip(),
            require_full_context=full_context_cb.value,
            from_alias=self._alias,
            in_reply_to=self._message,
        )
        self.dismiss(intent)

    def action_cancel(self) -> None:
        """Dismiss with None to signal cancellation."""
        self.dismiss(None)
