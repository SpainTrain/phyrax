"""ChatScreen — suspend-per-turn AI mailbox assistant.

'?' pushes a capture modal. On submit, the TUI suspends and the agent runs
interactively with a preamble documenting the phr CLI surface and inbox state.
On agent exit, the TUI resumes and config is re-loaded atomically.
No in-TUI scrollback — the agent's own terminal UI is the chat.
"""

from __future__ import annotations
