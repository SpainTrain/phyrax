"""Pydantic v2 configuration models and XDG-compliant path constants.

config.json is AI-owned — it is written by PhyraxConfig.save() and mutated
by the AI agent via the phr headless CLI. Humans should not edit it directly.
"""

from __future__ import annotations


def load() -> None:
    """Load PhyraxConfig from disk, returning defaults if the file is missing."""
    raise NotImplementedError


def save() -> None:
    """Atomically write config to disk (write .tmp, then os.rename)."""
    raise NotImplementedError
