"""FTUX bootstrap wizard and post-bootstrap ChatScreen handoff.

The wizard only asks for the AI CLI command (validates binary on PATH).
Everything else — identity, aliases, bundles, task action — is configured
by the AI agent in ChatScreen after the bootstrap completes.
"""

from __future__ import annotations


def run_bootstrap_wizard() -> object:
    """Present AI CLI selection screen and return a populated AIConfig.

    Presets: Claude Code, Gemini CLI, Goose, OpenCode, Custom.
    Validates binary with shutil.which(); warns but allows bypass if not found.
    """
    raise NotImplementedError


def run_post_bootstrap_handoff(app: object) -> None:
    """Push ChatScreen with a seeded preamble for first-run configuration.

    The preamble instructs the agent to collect identity.primary, aliases,
    at least one bundle, and copy a task template from docs/actions/ to ACTIONS_DIR.
    Only fires when config.is_first_run was True at app mount.
    """
    raise NotImplementedError
