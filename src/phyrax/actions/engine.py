"""Action template parser and executor.

Templates are YAML-frontmattered Markdown files in ACTIONS_DIR (~/.config/phyrax/actions/).
docs/actions/*.md ships read-only examples; FTUX/chat copies chosen ones to ACTIONS_DIR.

Frontmatter schema:
    name: str
    description: str
    require_full_context: bool  # default False
    allow_attachments: bool     # default False
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ActionTemplate:
    """A parsed action template ready for execution."""

    name: str
    description: str
    prompt_body: str
    require_full_context: bool
    allow_attachments: bool
    source_path: str


def list_actions() -> list[ActionTemplate]:
    """Scan ACTIONS_DIR for *.md files and return parsed ActionTemplates.

    Malformed files are logged at WARN and skipped (not fatal).
    Returns an empty list if ACTIONS_DIR does not exist.
    """
    raise NotImplementedError


def execute_action(
    template: ActionTemplate,
    message: object,
    config: object,
) -> int:
    """Compile a prompt and run the agent interactively.

    The caller is responsible for suspending the TUI via App.suspend() before
    calling this function.

    Returns:
        The agent's exit code.

    Raises:
        AgentError: If the agent subprocess cannot be spawned.
    """
    raise NotImplementedError
