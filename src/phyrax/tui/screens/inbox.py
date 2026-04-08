"""InboxScreen — the default Phyrax screen.

Shows bundles (priority-sorted, selectable headers) interleaved with unbundled
threads. Bundle headers and thread rows share a single cursor. Cursor stops at
boundaries (no wrap). Keybindings are read from config.keys.
"""

from __future__ import annotations
