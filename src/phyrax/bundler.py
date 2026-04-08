"""Bundle rule matching engine (pure functions, no I/O).

Bundles are evaluated in ascending priority order (0 = highest); the first
matching rule across all of a bundle's rules wins. Matching is stateless and
side-effect-free — all mutations (tagging, config writes) are handled by callers.
"""

from __future__ import annotations


def sort_bundles(config: object) -> list[object]:
    """Return bundles sorted ascending by priority (stable, 0 = highest)."""
    raise NotImplementedError


def match_thread_to_bundle(
    thread_headers: dict[str, str],
    bundles: list[object],
) -> object | None:
    """Evaluate priority-sorted bundles and return the first match, or None."""
    raise NotImplementedError


def apply_bundle_tags(db: object, thread_id: str, bundle: object) -> None:
    """Add the bundle's label tag to every message in the thread (idempotent)."""
    raise NotImplementedError


def generate_bundle_rule(
    message: object,
    user_description: str,
    config: object,
) -> object:
    """Call the AI agent in captured mode to propose a BundleRule.

    Raises:
        AgentError: If the agent output cannot be parsed as a BundleRule.
    """
    raise NotImplementedError
