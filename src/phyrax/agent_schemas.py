"""Pydantic v2 models for structured AI agent response payloads.

Every code path that calls the AI agent in captured mode and expects JSON
output must validate the raw stdout through one of these models.  Raw
``json.loads()`` plus dict indexing is forbidden — use
``SomeSchema.model_validate_json(raw)`` instead so that field presence,
type, and constraint errors surface as a typed ``AgentError`` rather than
an opaque ``KeyError`` or ``TypeError`` at call sites.

Usage example::

    from phyrax.agent_schemas import BundleRuleResponse
    from phyrax.exceptions import AgentError

    try:
        schema = BundleRuleResponse.model_validate_json(result.stdout.strip())
    except Exception as exc:
        raise AgentError(f"Bad agent output: {result.stdout!r}") from exc
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class BundleRuleResponse(BaseModel):
    """Shape of the JSON object the AI agent returns for bundle-rule proposals.

    Matches the :class:`~phyrax.config.BundleRule` model but is kept
    separate so that the agent output boundary is an explicit validation
    layer independent of the config model.

    Example agent output::

        {"field": "from", "operator": "contains", "value": "newsletters"}

    For the ``exists`` operator the ``value`` key may be omitted entirely::

        {"field": "header:List-Id", "operator": "exists"}
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    operator: Literal["contains", "equals", "matches", "exists"]
    value: str | None = None

    @model_validator(mode="after")
    def _validate_operator_value_constraint(self) -> BundleRuleResponse:
        if self.operator == "exists" and self.value is not None:
            raise ValueError("operator 'exists' must not have a value")
        if self.operator != "exists" and self.value is None:
            raise ValueError(f"operator '{self.operator}' requires a value")
        return self
