"""Tests for phyrax.agent_schemas — Pydantic validation of AI agent responses."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from phyrax.agent_schemas import BundleRuleResponse

# ---------------------------------------------------------------------------
# BundleRuleResponse — valid inputs
# ---------------------------------------------------------------------------


def test_bundle_rule_response_contains_operator() -> None:
    """A valid 'contains' payload round-trips through BundleRuleResponse."""
    raw = json.dumps({"field": "from", "operator": "contains", "value": "newsletters"})
    schema = BundleRuleResponse.model_validate_json(raw)
    assert schema.field == "from"
    assert schema.operator == "contains"
    assert schema.value == "newsletters"


def test_bundle_rule_response_equals_operator() -> None:
    """A valid 'equals' payload is accepted."""
    raw = json.dumps({"field": "to", "operator": "equals", "value": "boss@corp.com"})
    schema = BundleRuleResponse.model_validate_json(raw)
    assert schema.operator == "equals"
    assert schema.value == "boss@corp.com"


def test_bundle_rule_response_matches_operator() -> None:
    """A valid 'matches' payload is accepted."""
    raw = json.dumps({"field": "subject", "operator": "matches", "value": r"^Alert:"})
    schema = BundleRuleResponse.model_validate_json(raw)
    assert schema.operator == "matches"


def test_bundle_rule_response_exists_operator_no_value() -> None:
    """A valid 'exists' payload without a value field is accepted."""
    raw = json.dumps({"field": "header:List-Id", "operator": "exists"})
    schema = BundleRuleResponse.model_validate_json(raw)
    assert schema.operator == "exists"
    assert schema.value is None


def test_bundle_rule_response_exists_operator_null_value() -> None:
    """An 'exists' payload with explicit null value is accepted."""
    raw = json.dumps({"field": "header:List-Id", "operator": "exists", "value": None})
    schema = BundleRuleResponse.model_validate_json(raw)
    assert schema.value is None


# ---------------------------------------------------------------------------
# BundleRuleResponse — invalid inputs raise ValidationError
# ---------------------------------------------------------------------------


def test_bundle_rule_response_bad_json_raises_validation_error() -> None:
    """Completely invalid JSON raises ValidationError (not a bare json.JSONDecodeError)."""
    with pytest.raises(ValidationError):
        BundleRuleResponse.model_validate_json("not json at all")


def test_bundle_rule_response_unknown_operator_raises() -> None:
    """An unrecognised operator value raises ValidationError."""
    raw = json.dumps({"field": "from", "operator": "startswith", "value": "foo"})
    with pytest.raises(ValidationError):
        BundleRuleResponse.model_validate_json(raw)


def test_bundle_rule_response_extra_field_raises() -> None:
    """Extra fields in the payload raise ValidationError (extra='forbid')."""
    raw = json.dumps({"field": "from", "operator": "contains", "value": "foo", "extra": "bad"})
    with pytest.raises(ValidationError):
        BundleRuleResponse.model_validate_json(raw)


def test_bundle_rule_response_missing_field_raises() -> None:
    """Missing required 'field' key raises ValidationError."""
    raw = json.dumps({"operator": "contains", "value": "foo"})
    with pytest.raises(ValidationError):
        BundleRuleResponse.model_validate_json(raw)


def test_bundle_rule_response_missing_operator_raises() -> None:
    """Missing required 'operator' key raises ValidationError."""
    raw = json.dumps({"field": "from", "value": "foo"})
    with pytest.raises(ValidationError):
        BundleRuleResponse.model_validate_json(raw)


def test_bundle_rule_response_contains_without_value_raises() -> None:
    """'contains' operator without a value raises ValidationError."""
    raw = json.dumps({"field": "from", "operator": "contains"})
    with pytest.raises(ValidationError):
        BundleRuleResponse.model_validate_json(raw)


def test_bundle_rule_response_exists_with_value_raises() -> None:
    """'exists' operator with a non-null value raises ValidationError."""
    raw = json.dumps({"field": "from", "operator": "exists", "value": "something"})
    with pytest.raises(ValidationError):
        BundleRuleResponse.model_validate_json(raw)


def test_bundle_rule_response_empty_object_raises() -> None:
    """An empty JSON object raises ValidationError."""
    with pytest.raises(ValidationError):
        BundleRuleResponse.model_validate_json("{}")


def test_bundle_rule_response_empty_string_raises() -> None:
    """An empty string raises ValidationError."""
    with pytest.raises(ValidationError):
        BundleRuleResponse.model_validate_json("")
