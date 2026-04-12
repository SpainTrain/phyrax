"""Bundle rule matching engine (pure functions, no I/O).

Bundles are evaluated in ascending priority order (0 = highest); the first
matching rule across all of a bundle's rules wins. Matching is stateless and
side-effect-free — all mutations (tagging, config writes) are handled by callers.
"""

from __future__ import annotations

import re

from pydantic import ValidationError

from phyrax.agent_schemas import BundleRuleResponse
from phyrax.config import Bundle, BundleRule, PhyraxConfig
from phyrax.database import Database
from phyrax.exceptions import AgentError
from phyrax.models import MessageDetail


def sort_bundles(config: PhyraxConfig) -> list[Bundle]:
    """Return bundles sorted ascending by priority (stable, 0 = highest)."""
    return sorted(config.bundles, key=lambda b: b.priority)


def _get_field_value(thread_headers: dict[str, str], field: str) -> str:
    """Extract the header value for a given field name.

    Supports named fields (from, to, subject) and the generic
    ``header:<Name>`` syntax for arbitrary headers.
    """
    _named: dict[str, str] = {
        "from": "From",
        "to": "To",
        "subject": "Subject",
    }
    if field in _named:
        return thread_headers.get(_named[field], "")
    if field.startswith("header:"):
        header_name = field[len("header:") :]
        return thread_headers.get(header_name, "")
    # Unknown field — treat as absent.
    return ""


def _rule_matches(rule: BundleRule, thread_headers: dict[str, str]) -> bool:
    """Return True if *rule* matches the given thread headers."""
    field_value = _get_field_value(thread_headers, rule.field)

    if rule.operator == "exists":
        return bool(field_value)

    # All remaining operators require a non-None value (enforced by BundleRule).
    assert rule.value is not None
    value = rule.value

    if rule.operator == "contains":
        return value.lower() in field_value.lower()
    if rule.operator == "equals":
        return field_value.lower() == value.lower()
    if rule.operator == "matches":
        return bool(re.search(value, field_value, re.IGNORECASE))

    # Unreachable — Literal type prevents unknown operators.
    return False  # pragma: no cover


def match_thread_to_bundle(
    thread_headers: dict[str, str],
    bundles: list[Bundle],
) -> Bundle | None:
    """Evaluate priority-sorted bundles and return the first match, or None.

    ``bundles`` must already be sorted ascending by priority (caller's
    responsibility — use :func:`sort_bundles`).  Within each bundle the rules
    are OR-combined: the bundle matches if *any* rule matches.
    """
    for bundle in bundles:
        if any(_rule_matches(rule, thread_headers) for rule in bundle.rules):
            return bundle
    return None


def apply_bundle_tags(db: Database, thread_id: str, bundle: Bundle) -> None:
    """Add the bundle's label tag to every message in the thread (idempotent)."""
    db.add_tags(thread_id, [bundle.label])


def generate_bundle_rule(
    message: MessageDetail,
    user_description: str,
    config: PhyraxConfig,
) -> BundleRule:
    """Call the AI agent in captured mode to propose a BundleRule.

    Sends the email payload and the user's description to the AI agent and
    parses the JSON response into a :class:`~phyrax.config.BundleRule`.

    Raises:
        AgentError: If the agent output cannot be parsed as a BundleRule.
    """
    from phyrax.agent import RunMode, compile_prompt, run_agent

    system_prompt = (
        f"The user says: {user_description}\n\n"
        "Analyze the email and propose a BundleRule as JSON:\n"
        '{"field": "from|to|subject|header:<Name>", '
        '"operator": "contains|equals|matches|exists", "value": "..."}\n\n'
        "For the 'exists' operator, omit \"value\".\n"
        "Respond with ONLY the JSON object, no explanation."
    )

    prompt_path = compile_prompt(system_prompt, message)
    try:
        result = run_agent(config.ai.agent_command, prompt_path, mode=RunMode.CAPTURED)
    finally:
        prompt_path.unlink(missing_ok=True)

    try:
        response = BundleRuleResponse.model_validate_json(result.stdout.strip())
    except (ValidationError, ValueError) as exc:
        raise AgentError(
            f"Could not parse bundle rule from agent output: {result.stdout!r}"
        ) from exc

    return BundleRule(
        field=response.field,
        operator=response.operator,
        value=response.value,
    )
