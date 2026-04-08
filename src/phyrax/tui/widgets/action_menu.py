"""ActionMenu — overlay action picker (Space key).

Lists all actions from list_actions(). On select, suspends TUI and calls
execute_action(), then resumes on agent exit.
"""

from __future__ import annotations
