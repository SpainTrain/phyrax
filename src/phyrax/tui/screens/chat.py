"""ChatScreen — suspend-per-turn AI mailbox assistant.

'?' pushes a capture modal. On submit, the TUI suspends and the agent runs
interactively with a preamble documenting the phr CLI surface and inbox state.
On agent exit, the TUI resumes and config is re-loaded atomically.
No in-TUI scrollback — the agent's own terminal UI is the chat.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Label


class ChatScreen(Screen):  # type: ignore[type-arg]  # Textual Screen is generic at runtime
    """Full-screen AI chat interface using the suspend-per-turn model."""

    def __init__(self, preamble: str = "") -> None:
        super().__init__()
        self.preamble = preamble

    def compose(self) -> ComposeResult:
        yield Label("ChatScreen — not yet implemented")
