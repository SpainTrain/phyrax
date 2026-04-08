"""ComposeModal — reply intent capture.

Pushed by 'r' from InboxScreen or ThreadViewScreen. Always anchored to the
newest message in the thread. Captures AI instructions and a 'full thread
context' toggle, then hands off to the composer pipeline.
"""

from __future__ import annotations
