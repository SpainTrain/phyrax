"""FeedbackModal — captures user description of email miscategorization."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class FeedbackModal(ModalScreen[str | None]):
    """Ask the user to describe why a thread was miscategorized.

    Dismisses with the user's description string, or None if cancelled.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS_PATH = "feedback_modal.tcss"

    def __init__(self, thread_subject: str) -> None:
        super().__init__()
        self._subject = thread_subject

    def compose(self) -> ComposeResult:
        with Vertical(id="feedback-panel"):
            yield Label(f"Why is '{self._subject}' miscategorized?")
            yield Input(
                placeholder="Describe the correct bundle or rule\u2026",
                id="feedback-input",
            )

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        """Submit when Enter is pressed inside the input field."""
        self.action_submit()

    def action_submit(self) -> None:
        """Dismiss with the trimmed input value, or None if empty."""
        inp = self.query_one("#feedback-input", Input)
        self.dismiss(inp.value.strip() or None)

    def action_cancel(self) -> None:
        """Dismiss with None when Escape is pressed."""
        self.dismiss(None)
