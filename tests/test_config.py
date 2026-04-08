"""Tests for phyrax.config — load/save/validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from phyrax.config import PhyraxConfig
from phyrax.exceptions import ConfigError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_path(tmp_config_dir: Path) -> Path:
    return tmp_config_dir / "config" / "phyrax" / "config.json"


def _write_config(tmp_config_dir: Path, data: dict[str, object]) -> Path:
    path = _config_path(tmp_config_dir)
    path.write_text(json.dumps(data))
    return path


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------


def test_load_valid_json(tmp_config_dir: Path) -> None:
    path = _write_config(
        tmp_config_dir,
        {
            "identity": {"primary": "me@example.com", "aliases": ["alt@example.com"]},
            "ai": {"agent_command": "gemini -p %s"},
        },
    )
    cfg = PhyraxConfig.load(path)
    assert cfg.identity.primary == "me@example.com"
    assert cfg.identity.aliases == ["alt@example.com"]
    assert cfg.ai.agent_command == "gemini -p %s"


def test_load_missing_file_returns_defaults(tmp_path: Path) -> None:
    path = tmp_path / "nonexistent" / "config.json"
    assert not path.exists()
    cfg = PhyraxConfig.load(path)
    assert cfg.ai.agent_command == "claude -p %s"
    assert cfg.bundles == []
    assert cfg.compose.include_quote is True


def test_load_partial_json_fills_defaults(tmp_config_dir: Path) -> None:
    path = _write_config(tmp_config_dir, {"identity": {"primary": "x@y.com"}})
    cfg = PhyraxConfig.load(path)
    assert cfg.identity.primary == "x@y.com"
    # Fields not in JSON get defaults
    assert cfg.ai.agent_command == "claude -p %s"
    assert cfg.display.date_format == "relative"


def test_load_invalid_json_raises_config_error(tmp_config_dir: Path) -> None:
    path = _config_path(tmp_config_dir)
    path.write_text("{not valid json")
    with pytest.raises(ConfigError, match="Invalid JSON"):
        PhyraxConfig.load(path)


def test_is_first_run_true_when_file_missing(tmp_path: Path) -> None:
    path = tmp_path / "no_config" / "config.json"
    cfg = PhyraxConfig.load(path)
    assert cfg.is_first_run is True


def test_is_first_run_false_when_file_exists(tmp_config_dir: Path) -> None:
    path = _write_config(tmp_config_dir, {})
    cfg = PhyraxConfig.load(path)
    assert cfg.is_first_run is False


# ---------------------------------------------------------------------------
# save() and roundtrip
# ---------------------------------------------------------------------------


def test_save_reload_roundtrip(tmp_config_dir: Path) -> None:
    path = _config_path(tmp_config_dir)
    cfg = PhyraxConfig(
        identity={"primary": "a@b.com", "aliases": ["c@d.com"]},  # type: ignore[arg-type]
    )
    cfg.save(path)
    reloaded = PhyraxConfig.load(path)
    assert reloaded.identity.primary == "a@b.com"
    assert reloaded.identity.aliases == ["c@d.com"]


def test_save_writes_to_disk(tmp_config_dir: Path) -> None:
    path = _config_path(tmp_config_dir)
    cfg = PhyraxConfig()
    cfg.save(path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert "ai" in data
    assert "bundles" in data


def test_save_atomic_no_tmp_on_success(tmp_config_dir: Path) -> None:
    """After a successful save, no .tmp file should remain."""
    path = _config_path(tmp_config_dir)
    PhyraxConfig().save(path)
    tmp_files = list(path.parent.glob("*.tmp"))
    assert tmp_files == []


def test_save_does_not_overwrite_original_on_partial_failure(
    tmp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If os.rename raises, the original file must survive intact."""
    path = _config_path(tmp_config_dir)
    original_content = json.dumps({"identity": {"primary": "safe@example.com"}})
    path.write_text(original_content)

    import os

    def bad_rename(src: str, dst: str) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "rename", bad_rename)

    with pytest.raises(OSError, match="simulated rename failure"):
        PhyraxConfig().save(path)

    # Original must be intact
    assert path.read_text() == original_content


# ---------------------------------------------------------------------------
# BundleRule validation
# ---------------------------------------------------------------------------


def test_bundle_rule_exists_with_value_raises() -> None:
    with pytest.raises(ValidationError, match="exists"):
        from phyrax.config import BundleRule

        BundleRule(field="from", operator="exists", value="foo")


def test_bundle_rule_contains_with_no_value_raises() -> None:
    with pytest.raises(ValidationError, match="requires a value"):
        from phyrax.config import BundleRule

        BundleRule(field="from", operator="contains", value=None)


def test_bundle_rule_exists_without_value_valid() -> None:
    from phyrax.config import BundleRule

    rule = BundleRule(field="from", operator="exists")
    assert rule.value is None


def test_bundle_rule_contains_with_value_valid() -> None:
    from phyrax.config import BundleRule

    rule = BundleRule(field="from", operator="contains", value="substack.com")
    assert rule.value == "substack.com"


# ---------------------------------------------------------------------------
# Key defaults
# ---------------------------------------------------------------------------


def test_default_keys_present(tmp_config_dir: Path) -> None:
    path = _config_path(tmp_config_dir)
    cfg = PhyraxConfig.load(path)
    assert cfg.keys["archive"] == "a"
    assert cfg.keys["reply"] == "r"
    assert cfg.keys["chat"] == "question_mark"
