"""Domain exception hierarchy for Phyrax.

All exceptions raised by Phyrax should be subclasses of PhyraxError so that
callers can handle the full surface with a single except clause when needed.
"""

from __future__ import annotations


class PhyraxError(Exception):
    """Base class for all Phyrax exceptions."""


class ConfigError(PhyraxError):
    """Raised when config.json is missing, malformed, or fails validation."""


class DatabaseError(PhyraxError):
    """Raised when the notmuch database is unavailable or returns an error."""


class AgentError(PhyraxError):
    """Raised when an AI agent subprocess fails or returns unparseable output."""


class ComposeError(PhyraxError):
    """Raised when a draft file is malformed or cannot be parsed."""


class SendError(PhyraxError):
    """Raised when dispatching a draft via gmi send fails."""


class LockfileError(PhyraxError):
    """Raised when the PID lockfile cannot be acquired."""
