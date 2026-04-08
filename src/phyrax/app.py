"""PhyraxApp — Textual App subclass and TUI entrypoint.

On mount: acquires PID lockfile, loads config, opens Database. If first run,
routes to FTUX bootstrap + ChatScreen handoff before showing InboxScreen.
"""

from __future__ import annotations
