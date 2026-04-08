"""AI subprocess launcher — agent-agnostic prompt compilation and execution.

Two execution modes:
- Captured: stdout/stderr captured, TUI stays active (for draft gen, feedback).
- Interactive: stdio inherited, TUI suspended (for actions, chat, task).

The command template comes from config.ai.agent_command; ``%s`` is replaced
with the path to the compiled prompt temp file.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunMode(Enum):
    CAPTURED = "captured"
    INTERACTIVE = "interactive"


@dataclass
class AgentResult:
    """Result from a captured-mode agent run."""

    stdout: str
    stderr: str
    returncode: int


def compile_prompt(
    user_prompt: str,
    email_payload: str,
    *,
    require_full_context: bool = False,
    allow_attachments: bool = False,
) -> str:
    """Write an XML-structured prompt to a temp file and return its path.

    The prompt structure matches ARCHITECTURE.md §8.1:
      <system>…</system>
      <user_prompt>…</user_prompt>
      <email_payload>…</email_payload>

    Base64 MIME parts are stripped unless allow_attachments is True.
    Quote lines (starting with '>') are removed unless require_full_context is True.
    Only From/To/Cc/Date/Subject/Message-ID headers are included.
    """
    raise NotImplementedError


def run_agent(
    command: str,
    prompt_path: str,
    *,
    mode: RunMode = RunMode.CAPTURED,
    fallback_command: str | None = None,
) -> AgentResult:
    """Run the agent subprocess and return the result.

    ``%s`` in command is replaced with prompt_path via shlex.
    On non-zero exit and fallback_command set, retries once with the fallback.

    Raises:
        AgentError: If primary (and fallback) exit non-zero.
    """
    raise NotImplementedError


def run_agent_interactive(
    command: str,
    prompt_path: str,
    *,
    fallback_command: str | None = None,
) -> int:
    """Run the agent with inherited stdio (caller must suspend TUI first).

    Returns:
        The agent's exit code.
    """
    raise NotImplementedError
