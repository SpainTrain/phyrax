"""ThreadViewScreen — single-thread message reader.

Displays all messages chronologically. HTML-only messages are converted via
html2text for display. Reply (r) is always anchored to the newest message.
ctrl+g opens the thread in Gmail web UI.
"""

from __future__ import annotations
