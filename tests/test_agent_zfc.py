"""ZFC (Zero Framework Cognition) regression tests for agent output validation.

These tests ensure that phyrax.bundler.generate_bundle_rule() — and any future
caller that processes AI agent stdout — raises AgentError loudly when the agent
returns unstructured, free-form output instead of valid JSON.

The ZFC rule (CLAUDE.md §Key Architectural Rules #8):
  All reasoning must go through the external AI agent subprocess.  Code that
  silently swallows a parse error and returns a hardcoded default violates ZFC
  because it substitutes an in-process heuristic for the agent's judgment.

Anti-pattern under test (DO NOT ADD THIS):

    # WRONG — silent fallback hides bad agent output
    try:
        response = BundleRuleResponse.model_validate_json(result.stdout.strip())
    except Exception:
        # Silently return a default rule instead of surfacing the error.
        return BundleRule(field="from", operator="contains", value="example")

The tests below confirm that the production code never does this: unstructured
agent output always propagates as AgentError to the caller.
"""

from __future__ import annotations

import json
import stat
import textwrap
from pathlib import Path

import pytest

from phyrax.bundler import generate_bundle_rule
from phyrax.config import PhyraxConfig
from phyrax.exceptions import AgentError
from phyrax.models import MessageDetail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_script(tmp_path: Path, output: str, *, exit_code: int = 0) -> str:
    """Return path to a Python script that prints *output* on stdout and exits with *exit_code*.

    Uses a Python shebang instead of sh so that arbitrary bytes (including
    backticks and other shell-special characters) can be embedded in the output
    without risk of quoting issues or ENOEXEC on WSL2.
    """
    script = tmp_path / "fake_agent.py"
    # Write output as a Python bytes literal to sidestep all shell quoting.
    output_repr = repr(output)
    script.write_text(
        textwrap.dedent(f"""\
            #!/usr/bin/env python3
            import sys
            sys.stdout.write({output_repr})
            sys.exit({exit_code})
        """)
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(script)


def _make_message(**overrides: object) -> MessageDetail:
    defaults: dict[str, object] = dict(
        message_id="<zfc-test@fixture>",
        thread_id="thread-zfc",
        from_="sender@example.com",
        to=["me@example.com"],
        cc=[],
        date=1_735_732_800,
        subject="ZFC Test Subject",
        headers={},
        body_plain="Hello ZFC world",
        body_html=None,
        tags=frozenset({"inbox", "unread"}),
        attachments=[],
    )
    defaults.update(overrides)
    return MessageDetail(**defaults)  # type: ignore[arg-type]


def _make_config(script_path: str) -> PhyraxConfig:
    """Return a PhyraxConfig whose agent_command points at *script_path*."""
    ai_cls = PhyraxConfig.model_fields["ai"].default.__class__
    return PhyraxConfig(ai=ai_cls(agent_command=f"{script_path} %s"))


# ---------------------------------------------------------------------------
# ZFC regression: unstructured free-form text must raise AgentError
# ---------------------------------------------------------------------------


def test_free_form_text_raises_agent_error(tmp_path: Path) -> None:
    """Conversational free-form agent output is rejected loudly with AgentError.

    This is the core ZFC regression: the AI agent returned a natural-language
    sentence instead of a JSON object.  The validation layer must raise
    AgentError rather than swallow the error or return a default value.
    """
    script = _make_agent_script(tmp_path, "Yeah, looks like a newsletter to me!")
    config = _make_config(script)
    message = _make_message()

    with pytest.raises(AgentError, match="Could not parse bundle rule"):
        generate_bundle_rule(message, "classify this email", config)


def test_empty_output_raises_agent_error(tmp_path: Path) -> None:
    """Empty agent stdout is rejected loudly with AgentError.

    An agent that emits nothing (e.g., a model that silently terminates early)
    must not be treated as a valid response.
    """
    script = _make_agent_script(tmp_path, "")
    config = _make_config(script)
    message = _make_message()

    with pytest.raises(AgentError, match="Could not parse bundle rule"):
        generate_bundle_rule(message, "classify this email", config)


def test_prose_with_embedded_json_raises_agent_error(tmp_path: Path) -> None:
    """JSON buried inside prose is not extracted; the full output must be valid JSON.

    An agent that wraps its JSON in explanation text like
    'Sure, here you go: {"field": "from", ...}' must still fail validation.
    The code must not scan the output for JSON fragments.
    """
    payload = json.dumps({"field": "from", "operator": "contains", "value": "newsletters"})
    output = f"Sure, here is the rule you asked for: {payload}"
    script = _make_agent_script(tmp_path, output)
    config = _make_config(script)
    message = _make_message()

    with pytest.raises(AgentError, match="Could not parse bundle rule"):
        generate_bundle_rule(message, "classify this email", config)


def test_markdown_code_fence_raises_agent_error(tmp_path: Path) -> None:
    """JSON inside a markdown code fence is not valid output.

    Some models wrap JSON in triple-backtick blocks.  The validator must reject
    this: scanning for fence boundaries is an in-process heuristic and violates ZFC.
    """
    payload = json.dumps({"field": "from", "operator": "contains", "value": "newsletters"})
    output = f"```json\n{payload}\n```"
    script = _make_agent_script(tmp_path, output)
    config = _make_config(script)
    message = _make_message()

    with pytest.raises(AgentError, match="Could not parse bundle rule"):
        generate_bundle_rule(message, "classify this email", config)


def test_invalid_operator_raises_agent_error(tmp_path: Path) -> None:
    """JSON with an unknown operator value is rejected loudly with AgentError.

    The schema only allows 'contains', 'equals', 'matches', 'exists'.
    Any other value (including plausible ones like 'startswith') must fail.
    """
    payload = json.dumps({"field": "from", "operator": "startswith", "value": "news"})
    script = _make_agent_script(tmp_path, payload)
    config = _make_config(script)
    message = _make_message()

    with pytest.raises(AgentError, match="Could not parse bundle rule"):
        generate_bundle_rule(message, "classify this email", config)


def test_missing_required_field_raises_agent_error(tmp_path: Path) -> None:
    """JSON missing the required 'field' key is rejected loudly with AgentError."""
    payload = json.dumps({"operator": "contains", "value": "newsletters"})
    script = _make_agent_script(tmp_path, payload)
    config = _make_config(script)
    message = _make_message()

    with pytest.raises(AgentError, match="Could not parse bundle rule"):
        generate_bundle_rule(message, "classify this email", config)


def test_extra_keys_raise_agent_error(tmp_path: Path) -> None:
    """JSON with unexpected extra keys is rejected loudly with AgentError.

    BundleRuleResponse uses model_config = ConfigDict(extra='forbid'), so any
    undeclared key is a schema violation.  This prevents agents from sneaking
    in side-channel data that callers might silently ignore.
    """
    payload = json.dumps(
        {"field": "from", "operator": "contains", "value": "newsletters", "confidence": 0.97}
    )
    script = _make_agent_script(tmp_path, payload)
    config = _make_config(script)
    message = _make_message()

    with pytest.raises(AgentError, match="Could not parse bundle rule"):
        generate_bundle_rule(message, "classify this email", config)


def test_exists_operator_with_value_raises_agent_error(tmp_path: Path) -> None:
    """'exists' operator combined with a value violates the model_validator constraint.

    This tests that the cross-field validation rule in BundleRuleResponse is
    enforced: exists + value is a schema error, not a silently accepted edge case.
    """
    payload = json.dumps({"field": "header:List-Id", "operator": "exists", "value": "something"})
    script = _make_agent_script(tmp_path, payload)
    config = _make_config(script)
    message = _make_message()

    with pytest.raises(AgentError, match="Could not parse bundle rule"):
        generate_bundle_rule(message, "classify this email", config)


# ---------------------------------------------------------------------------
# ZFC anti-pattern guard: the silent-fallback wrapper must not exist
# ---------------------------------------------------------------------------


def test_no_silent_fallback_in_generate_bundle_rule(tmp_path: Path) -> None:
    """Regression: generate_bundle_rule must NOT silently return a default BundleRule.

    This test guards against the following anti-pattern being introduced:

        # WRONG — violates ZFC
        try:
            response = BundleRuleResponse.model_validate_json(result.stdout.strip())
        except Exception:
            return BundleRule(field="from", operator="contains", value="example")

    If that code path existed, this test would PASS (no exception raised) but
    the returned rule would be a lie — a hardcoded in-process heuristic masking
    a broken agent response.

    By asserting that AgentError IS raised, we ensure the silent fallback is
    absent.  If someone adds the anti-pattern, this test will fail because
    generate_bundle_rule will return instead of raising.
    """
    # Agent returns free-form text — cannot possibly be a valid BundleRule.
    script = _make_agent_script(tmp_path, "Yeah, looks like a newsletter to me!")
    config = _make_config(script)
    message = _make_message()

    # Must raise — never return silently.
    with pytest.raises(AgentError):
        generate_bundle_rule(message, "classify this email", config)


# ---------------------------------------------------------------------------
# Positive control: valid JSON is accepted
# ---------------------------------------------------------------------------


def test_valid_json_is_accepted(tmp_path: Path) -> None:
    """Positive control: a well-formed agent response produces a BundleRule without error.

    This test ensures that the validation layer is not over-restrictive — it
    must accept exactly the JSON shape specified by BundleRuleResponse.
    """
    from phyrax.config import BundleRule

    payload = json.dumps({"field": "from", "operator": "contains", "value": "newsletters"})
    script = _make_agent_script(tmp_path, payload)
    config = _make_config(script)
    message = _make_message()

    rule = generate_bundle_rule(message, "classify this email", config)

    assert isinstance(rule, BundleRule)
    assert rule.field == "from"
    assert rule.operator == "contains"
    assert rule.value == "newsletters"


def test_valid_json_exists_operator_is_accepted(tmp_path: Path) -> None:
    """Positive control: 'exists' operator without a value is valid."""
    from phyrax.config import BundleRule

    payload = json.dumps({"field": "header:List-Id", "operator": "exists"})
    script = _make_agent_script(tmp_path, payload)
    config = _make_config(script)
    message = _make_message()

    rule = generate_bundle_rule(message, "classify this email", config)

    assert isinstance(rule, BundleRule)
    assert rule.field == "header:List-Id"
    assert rule.operator == "exists"
    assert rule.value is None
