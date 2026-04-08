"""Pydantic v2 configuration models and XDG-compliant path constants.

config.json is AI-owned — it is written by PhyraxConfig.save() and mutated
by the AI agent via the phr headless CLI. Humans should not edit it directly.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Literal

import platformdirs
from pydantic import BaseModel, PrivateAttr, model_validator

from phyrax.exceptions import ConfigError

# ---------------------------------------------------------------------------
# XDG-compliant path constants
# ---------------------------------------------------------------------------

CONFIG_DIR: Path = Path(platformdirs.user_config_dir("phyrax"))
ACTIONS_DIR: Path = CONFIG_DIR / "actions"
DRAFTS_DIR: Path = Path(platformdirs.user_cache_dir("phyrax")) / "drafts"
STATE_DIR: Path = Path(platformdirs.user_state_dir("phyrax"))
LOCKFILE: Path = Path(platformdirs.user_cache_dir("phyrax")) / "phr.lock"

_CONFIG_FILE: Path = CONFIG_DIR / "config.json"

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class AIConfig(BaseModel):
    agent_command: str = "claude -p %s"
    fallback_command: str | None = None


class IdentityConfig(BaseModel):
    primary: str = ""
    aliases: list[str] = []


class TaskConfig(BaseModel):
    action: str | None = None


class BundleRule(BaseModel):
    field: str
    operator: Literal["contains", "equals", "matches", "exists"]
    value: str | None = None

    @model_validator(mode="after")
    def _exists_requires_no_value(self) -> BundleRule:
        if self.operator == "exists" and self.value is not None:
            raise ValueError("operator 'exists' must have value=None")
        if self.operator != "exists" and self.value is None:
            raise ValueError(f"operator '{self.operator}' requires a value")
        return self


class Bundle(BaseModel):
    name: str
    label: str
    rules: list[BundleRule]
    priority: int = 50


class ComposeConfig(BaseModel):
    include_quote: bool = True


class DisplayConfig(BaseModel):
    date_format: str = "relative"
    thread_preview_lines: int = 2
    bundle_collapsed_default: bool = True


_DEFAULT_KEYS: dict[str, str] = {
    "archive": "a",
    "reply": "r",
    "feedback": "f",
    "task": "t",
    "action": "space",
    "outbox": "o",
    "command_palette": "ctrl+p",
    "gmail_escape": "ctrl+g",
    "chat": "question_mark",
}


# ---------------------------------------------------------------------------
# Root config model
# ---------------------------------------------------------------------------


class PhyraxConfig(BaseModel):
    ai: AIConfig = AIConfig()
    identity: IdentityConfig = IdentityConfig()
    task: TaskConfig = TaskConfig()
    bundles: list[Bundle] = []
    compose: ComposeConfig = ComposeConfig()
    keys: dict[str, str] = _DEFAULT_KEYS.copy()
    display: DisplayConfig = DisplayConfig()

    # Private — not serialised into config.json; set by load() only.
    _is_first_run: bool = PrivateAttr(default=False)

    @property
    def is_first_run(self) -> bool:
        """True iff config.json did not exist when this config was loaded."""
        return self._is_first_run

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path = _CONFIG_FILE) -> PhyraxConfig:
        """Load from *path*, returning defaults if the file is missing.

        Raises:
            ConfigError: if the file exists but contains invalid JSON.
        """
        first_run = not path.exists()
        if first_run:
            instance = cls()
        else:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
            try:
                instance = cls.model_validate(raw)
            except Exception as exc:
                raise ConfigError(f"Config validation failed: {exc}") from exc

        instance._is_first_run = first_run
        return instance

    def save(self, path: Path = _CONFIG_FILE) -> None:
        """Atomically write config to *path* (write .tmp → os.rename)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(mode="json")
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.rename(tmp, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
