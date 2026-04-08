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

import logging
from dataclasses import dataclass, field
from pathlib import Path

from phyrax import agent as _agent
from phyrax.config import ACTIONS_DIR, PhyraxConfig
from phyrax.models import MessageDetail

_log = logging.getLogger("phyrax")


@dataclass
class ActionTemplate:
    """A parsed action template ready for execution."""

    name: str
    description: str
    prompt_body: str
    source_path: Path
    require_full_context: bool = field(default=False)
    allow_attachments: bool = field(default=False)


def _parse_frontmatter(text: str, source: Path) -> ActionTemplate | None:
    """Parse a YAML-frontmattered Markdown file.

    Returns an ActionTemplate on success, or None if the file is malformed
    (missing frontmatter, invalid YAML, or missing required keys).
    """
    # Files must start with '---'
    if not text.startswith("---"):
        _log.warning("action template %s has no frontmatter — skipping", source)
        return None

    # Split out the frontmatter block: first '---' to closing '---'
    # We strip the leading '---\n' then split on '\n---'
    rest = text[3:]  # strip opening '---'
    if rest.startswith("\n"):
        rest = rest[1:]

    parts = rest.split("\n---", maxsplit=1)
    if len(parts) < 2:
        _log.warning(
            "action template %s frontmatter is not closed — skipping", source
        )
        return None

    fm_block, body_block = parts

    # Parse the body — strip leading newline after closing '---\n'
    prompt_body = body_block.lstrip("\n")

    # Minimal key: value YAML parser (no pyyaml dependency)
    parsed: dict[str, str | bool] = {}
    for line in fm_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            _log.warning(
                "action template %s has invalid frontmatter line %r — skipping",
                source,
                line,
            )
            return None
        key, _, raw_value = line.partition(":")
        key = key.strip()
        raw_value = raw_value.strip()

        # Interpret booleans
        if raw_value.lower() == "true":
            parsed[key] = True
        elif raw_value.lower() == "false":
            parsed[key] = False
        else:
            # Strip optional surrounding quotes
            if (raw_value.startswith('"') and raw_value.endswith('"')) or (
                raw_value.startswith("'") and raw_value.endswith("'")
            ):
                raw_value = raw_value[1:-1]
            parsed[key] = raw_value

    # Validate required keys
    for required in ("name", "description"):
        if required not in parsed:
            _log.warning(
                "action template %s missing required frontmatter key %r — skipping",
                source,
                required,
            )
            return None

    name = parsed["name"]
    description = parsed["description"]

    if not isinstance(name, str) or not name:
        _log.warning(
            "action template %s has invalid 'name' field — skipping", source
        )
        return None

    if not isinstance(description, str) or not description:
        _log.warning(
            "action template %s has invalid 'description' field — skipping", source
        )
        return None

    require_full_context = parsed.get("require_full_context", False)
    if not isinstance(require_full_context, bool):
        _log.warning(
            "action template %s has non-boolean 'require_full_context' — skipping",
            source,
        )
        return None

    allow_attachments = parsed.get("allow_attachments", False)
    if not isinstance(allow_attachments, bool):
        _log.warning(
            "action template %s has non-boolean 'allow_attachments' — skipping",
            source,
        )
        return None

    return ActionTemplate(
        name=name,
        description=description,
        prompt_body=prompt_body,
        source_path=source,
        require_full_context=require_full_context,
        allow_attachments=allow_attachments,
    )


def list_actions(actions_dir: Path | None = None) -> list[ActionTemplate]:
    """Scan *actions_dir* for ``*.md`` files and return parsed ActionTemplates.

    Malformed files are logged at WARN and skipped (not fatal).
    Returns an empty list if *actions_dir* does not exist or is empty.
    """
    directory = actions_dir if actions_dir is not None else ACTIONS_DIR

    if not directory.exists() or not directory.is_dir():
        return []

    templates: list[ActionTemplate] = []
    for md_file in directory.glob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError as exc:
            _log.warning("could not read action template %s: %s — skipping", md_file, exc)
            continue

        template = _parse_frontmatter(text, md_file)
        if template is not None:
            templates.append(template)

    return sorted(templates, key=lambda t: t.name)


def execute_action(
    template: ActionTemplate,
    message: MessageDetail,
    config: PhyraxConfig,
) -> int:
    """Compile a prompt from *template* and run the agent interactively.

    The caller is responsible for suspending the TUI via App.suspend() before
    calling this function.

    Args:
        template: The parsed action template to execute.
        message: The currently selected message to pass as email payload.
        config: The loaded PhyraxConfig (provides ai.agent_command etc.).

    Returns:
        The agent's exit code (0 on success).

    Raises:
        AgentError: If the agent subprocess fails.
    """
    prompt_path = _agent.compile_prompt(
        template.prompt_body,
        message,
        require_full_context=template.require_full_context,
        allow_attachments=template.allow_attachments,
    )
    try:
        exit_code = _agent.run_agent_interactive(
            config.ai.agent_command,
            prompt_path,
            fallback_command=config.ai.fallback_command,
        )
    finally:
        prompt_path.unlink(missing_ok=True)
    return exit_code
