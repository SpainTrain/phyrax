"""BundleFocusScreen — filtered thread list for a single bundle.

Reuses ThreadListWidget with query ``tag:{bundle.label} AND tag:inbox``.
All InboxScreen keybindings work within the filtered context.
"""

from __future__ import annotations
