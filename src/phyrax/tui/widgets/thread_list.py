"""ThreadListWidget — virtualized, reactive thread + bundle header list.

Rows are either bundle headers (selectable, show count/unread) or thread rows
(sender as 'Name (domain.tld)', subject, relative date, unread indicator, tags).
Single shared cursor; j/k stop at boundaries. Rolling viewport queries the DB.
"""

from __future__ import annotations
