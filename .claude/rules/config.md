# Config Layer Rules

Actionable rules for reading and writing `config.json`.

## config.json is AI-Owned

`config.json` is written programmatically — by `PhyraxConfig.save()` and by the AI agent via the headless CLI. Humans may read it, but the canonical write path is always through `PhyraxConfig.save()`.

Do not add a Settings screen or palette entry that writes config.json via any other code path.

## Sole Write Path

`PhyraxConfig.save()` is the only sanctioned method for persisting config. It implements an atomic write:

```python
fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
os.rename(tmp, path)
```

Never open `config.json` for writing directly. Never call `Path.write_text()` on it. If you need to persist config state, load the current config, mutate the model, and call `.save()`.

## is_first_run Semantics

`PhyraxConfig.is_first_run` is `True` if and only if the config file did not exist on disk when `PhyraxConfig.load()` was called. It is stored as a `PrivateAttr` so it is never serialised into `config.json`.

Do not set `_is_first_run` anywhere other than inside `PhyraxConfig.load()`. Do not infer first-run status from any other condition (e.g., empty bundle list, missing AI command).

## Path Resolution

Use `platformdirs` for all directory resolution. Never hardcode paths like `~/.config/phyrax/`.

```python
import platformdirs

CONFIG_DIR = Path(platformdirs.user_config_dir("phyrax"))
STATE_DIR  = Path(platformdirs.user_state_dir("phyrax"))
CACHE_DIR  = Path(platformdirs.user_cache_dir("phyrax"))
```

This ensures XDG compliance on Linux and correct platform defaults on macOS and Windows if Phyrax is ever ported.

## Validation and Error Handling

Config is validated via `PhyraxConfig.model_validate(raw_dict)` immediately after JSON parsing. Any validation failure must raise `ConfigError` (from `phyrax.exceptions`), not a raw `pydantic.ValidationError`.

```python
try:
    instance = cls.model_validate(raw)
except Exception as exc:
    raise ConfigError(f"Config validation failed: {exc}") from exc
```

Invalid JSON (malformed file) must also raise `ConfigError`, not `json.JSONDecodeError`.
