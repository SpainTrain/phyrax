"""Built-in actions — the reserved 't' task creation flow.

The task action runs the user's configured task template interactively, then
prompts 'Task created? [y/N]'. Only on confirmation does Phyrax tag +task-created.
"""

from __future__ import annotations

from phyrax.models import ThreadSummary


def run_task_action(thread: ThreadSummary, config: object) -> None:
    """Execute the configured task action template for the given thread.

    If config.task.action is None, notifies the user to configure one via chat.
    Otherwise, runs the action template interactively and prompts for confirmation.
    Tags +task-created on every message in the thread only on 'y'.
    """
    raise NotImplementedError
