# General Coding Rules

Actionable baseline conventions for all Phyrax agents. These rules apply to every module.

## Linting and Formatting

Run ruff for both linting and formatting. Config is in `pyproject.toml`.

```bash
# Check and auto-fix
~/.local/bin/uv run ruff check --fix src/ tests/
~/.local/bin/uv run ruff format src/ tests/

# Type checking
~/.local/bin/uv run mypy src/phyrax/
```

Both must pass with zero errors before committing. Do not suppress mypy errors without a comment.

## Type Hints

- All public function signatures must have type hints on every parameter and the return value.
- Use `str | None` syntax, not `Optional[str]`. Python 3.12+ only; `Optional` is banned.
- Use `from __future__ import annotations` at the top of every module (enables forward references without runtime cost).

## Data Containers vs Config Models

- Use `@dataclass` for DTOs (transfer objects that are never serialised to JSON by the app).
- Use `pydantic.BaseModel` only for configuration models — things that are read from or written to `config.json`.
- Never use Pydantic for internal data structures that do not cross a serialisation boundary.

## `# type: ignore` Policy

Never write `# type: ignore` without an adjacent inline comment explaining why the suppression is necessary.

Acceptable example (from `database.py`):
```python
import notmuch2  # type: ignore[import-untyped]  # CFFI binding; no stub available
```

## Exception Handling

- Raise domain-specific exceptions defined in `src/phyrax/exceptions.py` (`ConfigError`, `DatabaseError`, etc.).
- Never catch bare `Exception` unless you are immediately re-raising or translating to a domain exception.
- Always catch the narrowest applicable exception type.

```python
# Correct
try:
    result = subprocess.run(cmd, check=True)
except subprocess.CalledProcessError as exc:
    raise DatabaseError("notmuch config get failed") from exc

# Wrong — too broad
try:
    result = subprocess.run(cmd, check=True)
except Exception as exc:
    raise DatabaseError("...") from exc
```

## Logging

```python
import logging
log = logging.getLogger("phyrax")
```

Use `log.warning(...)`, `log.error(...)`, etc. Do not use `print()` for diagnostics.
Log file location: `~/.local/state/phyrax/phyrax.log` (resolved via `platformdirs.user_state_dir("phyrax")`).

## Commit Messages

Use Conventional Commits format:

```
feat: add bundle priority sorting
fix: handle missing X-GM-THRID header gracefully
docs: update ARCHITECTURE.md §8 agent modes
refactor: extract _walk_mime into its own helper
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`.

## Import Rules

- `database.py` is the **sole** module that imports `notmuch2`. No other module may `import notmuch2`.
- No module may import any LLM SDK (`anthropic`, `google.generativeai`, `openai`, etc.). AI interaction is always via `agent.py` subprocess calls.
- Use `from __future__ import annotations` as the first non-comment import in every module.

## Config Mutation Safety

`PhyraxConfig.save()` is the only sanctioned way to write `config.json`. It uses an atomic write-then-rename pattern:

```python
fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
# ... write to fd ...
os.rename(tmp, path)
```

Never open `config.json` for writing directly. Never write config state to any other file.
