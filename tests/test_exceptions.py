"""Tests for phyrax.exceptions — exception hierarchy."""

from __future__ import annotations

from phyrax.exceptions import (
    AgentError,
    ComposeError,
    ConfigError,
    DatabaseError,
    LockfileError,
    PhyraxError,
    SendError,
)


def test_exception_hierarchy() -> None:
    """All domain exceptions inherit from PhyraxError."""
    for exc_class in (
        ConfigError,
        DatabaseError,
        AgentError,
        ComposeError,
        SendError,
        LockfileError,
    ):
        assert issubclass(exc_class, PhyraxError)
