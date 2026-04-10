"""ChatScreen — suspend-per-turn AI mailbox assistant.

'?' pushes a capture modal. On submit, the TUI suspends and the agent runs
interactively with a preamble documenting the phr CLI surface and inbox state.
On agent exit, the TUI resumes and config is re-loaded atomically.
No in-TUI scrollback — the agent's own terminal UI is the chat.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Input, Label

from phyrax.config import PhyraxConfig
from phyrax.database import Database

log = logging.getLogger("phyrax")

_CLI_CHEATSHEET = """\
Available phr commands:
  phr status              JSON: inbox totals, bundle counts, drafts pending
  phr list [--bundle=NAME] [--query=QUERY]  list threads (JSON)
  phr archive <thread_id>  archive a thread (removes inbox tag)
  phr tag <thread_id> +tag1 -tag2  modify tags
  phr compose --thread=<id> --body=-  stage a draft reply from stdin
"""


def _build_preamble(db: Database, config: PhyraxConfig, user_message: str) -> str:
    """Build the full prompt preamble for the AI agent."""
    inbox_unread = db.count_threads("tag:inbox tag:unread")
    inbox_total = db.count_threads("tag:inbox")

    bundle_lines = []
    for bundle in config.bundles[:5]:  # top 5 bundles
        count = db.count_threads(f"tag:{bundle.label}")
        unread = db.count_threads(f"tag:{bundle.label} tag:unread")
        bundle_lines.append(f"  {bundle.name}: {count} threads ({unread} unread)")

    bundles_str = "\n".join(bundle_lines) or "  (no bundles configured)"

    return (
        "You are a helpful assistant for the Phyrax email client.\n\n"
        "Current inbox state:\n"
        f"  Total: {inbox_total} threads\n"
        f"  Unread: {inbox_unread} threads\n\n"
        f"Bundles:\n{bundles_str}\n\n"
        f"{_CLI_CHEATSHEET}\n"
        f"User: {user_message or '(no specific request — help the user manage their email)'}\n"
    )


class _InputModal(ModalScreen[str]):
    """Tiny capture modal to collect an optional chat message from the user."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    _InputModal { align: center middle; }
    #chat-panel {
        width: 70; height: auto; padding: 1 2;
        border: solid $primary; background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="chat-panel"):
            yield Label("Chat with AI agent (Enter to start, blank = open session):")
            yield Input(id="chat-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dismiss with whatever the user typed (may be empty string)."""
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        """Dismiss with empty string on Escape."""
        self.dismiss("")


class ChatScreen(Screen[None]):
    """Full-screen AI chat interface using the suspend-per-turn model.

    Two modes:

    Normal mode (preamble=""):
      - Shows a capture modal for an optional user message.
      - Suspends the TUI, runs the agent with an inbox-state preamble.
      - On exit, reloads config and pops itself.

    FTUX mode (preamble=FIRST_RUN_PREAMBLE):
      - Shows a "Press Enter to start" prompt.
      - Suspends the TUI, runs the agent with the supplied preamble.
      - On exit, reloads config and pops itself.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "pop_screen", "Close"),
    ]

    def __init__(
        self,
        db: Database | None = None,
        config: PhyraxConfig | None = None,
        preamble: str = "",
    ) -> None:
        super().__init__()
        self._db = db
        self._config = config
        self.preamble = preamble

    def compose(self) -> ComposeResult:
        if self.preamble:
            yield Label("First-run AI setup — press Enter to begin, Escape to skip.")
        else:
            yield Label("Opening AI chat…")

    async def on_mount(self) -> None:
        """Collect optional user input, suspend, run agent, reload config, pop."""
        if self.preamble:
            # FTUX mode: wait for the user to press Enter before starting the agent.
            user_msg: str = await self.app.push_screen_wait(_InputModal())
            prompt_content = self.preamble + (f"\n\nUser: {user_msg}" if user_msg else "")
        else:
            # Normal mode: show modal, build inbox-state preamble.
            user_msg = await self.app.push_screen_wait(_InputModal())
            config = self._config or PhyraxConfig.load()
            if self._db:
                prompt_content = _build_preamble(self._db, config, user_msg)
            else:
                prompt_content = f"{_CLI_CHEATSHEET}\n\nUser: {user_msg or '(open session)'}\n"

        # Write preamble to a temp file and run the agent.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(prompt_content)
            prompt_path = Path(fh.name)

        try:
            from phyrax.agent import run_agent_interactive

            config_for_cmd = self._config or PhyraxConfig.load()
            with self.app.suspend():
                run_agent_interactive(config_for_cmd.ai.agent_command, prompt_path)
        except Exception as exc:
            log.error("Chat agent failed: %s", exc)
        finally:
            prompt_path.unlink(missing_ok=True)

        # Re-load config atomically — the AI may have updated it.
        try:
            PhyraxConfig.load()
        except Exception as exc:
            log.warning("Config reload after chat failed: %s", exc)

        self.app.pop_screen()
