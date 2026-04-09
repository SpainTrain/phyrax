"""Built-in actions — the reserved 't' task creation flow.

The task action runs the user's configured task template interactively, then
prompts 'Task created? [y/N]'. Only on confirmation does Phyrax tag +task-created.
"""

from __future__ import annotations

import logging

from phyrax.actions.engine import execute_action, list_actions
from phyrax.config import PhyraxConfig
from phyrax.database import Database
from phyrax.models import ThreadSummary

log = logging.getLogger("phyrax")


def run_task_action(db: Database, thread: ThreadSummary, config: PhyraxConfig) -> bool:
    """Execute the configured task action template for the given thread.

    The caller must suspend the TUI via App.suspend() before calling this
    function, because execute_action launches an interactive subprocess.

    Returns True if the action ran successfully (caller should prompt
    'Task created? [y/N]' and call db.add_tags on confirmation).
    Returns False if the action is not configured or the thread has no messages
    (no prompt should be shown; a notification has already been logged).

    Args:
        db: Open Database instance for tag mutations.
        thread: The currently selected thread.
        config: Loaded PhyraxConfig providing task.action and ai settings.
    """
    task_action_name = config.task.action
    if task_action_name is None:
        log.info("run_task_action: no task action configured — user must configure one via chat")
        return False

    actions = list_actions()
    template = next((a for a in actions if a.name == task_action_name), None)
    if template is None:
        log.warning(
            "run_task_action: configured task action %r not found in actions directory",
            task_action_name,
        )
        return False

    messages = db.get_thread_messages(thread.thread_id)
    if not messages:
        log.warning(
            "run_task_action: thread %r has no messages — cannot run action",
            thread.thread_id,
        )
        return False

    newest_msg = messages[-1]
    execute_action(template, newest_msg, config)
    return True
