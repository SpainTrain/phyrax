# Database Layer Rules

Actionable rules for any code that touches the notmuch database.

## Sole-Importer Constraint

`database.py` is the **only** module that may `import notmuch2`. This is enforced by convention and verified in code review.

- All other modules receive `ThreadSummary` or `MessageDetail` dataclasses returned by `Database` methods.
- No other module may hold a reference to a raw `notmuch2` object.
- If you need email data in a new module, add a method to `Database` and return a typed dataclass.

## DB Path Resolution

Resolve the database path in exactly one of two ways:

1. Via subprocess: `subprocess.run(["notmuch", "config", "get", "database.path"], ...)` — used in production.
2. Via explicit `path` argument to `Database.__init__` — used in tests.

Never hardcode a path. Never read `~/.notmuch-config` directly.

## Tag Mutations

All tag add/remove operations must use `db.atomic()` as a context manager:

```python
with self._db.atomic():
    for nm_msg in messages:
        nm_msg.tags.add("inbox")
```

Never mutate tags outside an `atomic()` block. This ensures notmuch's Xapian index stays consistent.

## Single Source of Truth

notmuch is the only data store for email state. Do not:

- Create a SQLite cache of thread metadata.
- Write JSON files containing thread IDs, tags, or message content.
- Maintain an in-memory shadow dict that persists across requests.

If data is not in notmuch, it does not exist.

## Test Requirements

Database tests must never touch a real mailbox. Use the fixture Maildir set up in `tests/conftest.py`.

Point tests at a fixture notmuch config via the environment variable:

```python
# In conftest.py or the test itself
monkeypatch.setenv("NOTMUCH_CONFIG", str(fixture_config_path))
```

`Database.__init__` accepts an explicit `path` argument; pass the fixture path rather than relying on the config-get subprocess.

## ThreadSummary.snippet Rules

The `snippet` field on `ThreadSummary` must satisfy all of the following:

- Maximum 200 characters (truncated at exactly 200; never longer).
- Quote lines (lines starting with `>` after stripping leading whitespace) are stripped before truncation.
- Remaining text is whitespace-collapsed: all runs of whitespace (including newlines) are replaced by a single space, and leading/trailing whitespace is removed.

Reference implementation: `_build_snippet()` and `_strip_quotes_and_collapse()` in `database.py`.
