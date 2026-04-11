# CLAUDE.md — Phyrax Project Instructions

This file provides instructions and context for AI coding agents working on this project.

## What is Phyrax?

Phyrax (`phr`) is a keyboard-first terminal email client that syncs Gmail via `lieer`, indexes with `notmuch`, and orchestrates AI agents for drafting, triaging, and task extraction. See `ARCHITECTURE.md` for full technical spec.

## Agent Rules

The `.claude/rules/` directory contains topic-specific, actionable rules for all agents working on this project. When implementing a feature, read the relevant rule file before writing code.

| File | Covers |
|---|---|
| `.claude/rules/general.md` | Ruff/mypy enforcement, type hints, imports, exception handling, logging, commit style, config atomicity |
| `.claude/rules/database.md` | notmuch sole-importer constraint, tag mutation safety, test fixture setup, snippet formatting |
| `.claude/rules/tui.md` | Subprocess suspension before $EDITOR/agent, keybinding config sourcing, Textual pilot tests, network isolation |
| `.claude/rules/config.md` | Sole write path via `PhyraxConfig.save()`, `is_first_run` semantics, platformdirs usage, validation error handling |
| `.claude/rules/devtools.md` | textual-dev usage, dev tooling conventions |

**When implementing a new epic**, add topic rules to `.claude/rules/` for patterns discovered during implementation. Rules must be actionable (what to do or not do) — not aspirational. Avoid "prefer X" or "consider Y"; write "always X" or "never Y".

## Tech Stack

- **Python ≥ 3.12**, packaged with **uv**
- **Textual** for TUI, **Typer** for headless CLI
- **notmuch2** (Python CFFI bindings) for all email database access
- **Pydantic v2** for configuration models
- **pandoc** for Markdown → HTML email rendering
- AI agents invoked as subprocesses (never imported as libraries)

## Repository Layout

```
src/phyrax/          # All application code
  cli.py             # Typer entrypoint — `phr` command
  app.py             # Textual App — TUI shell
  config.py          # Pydantic config models
  database.py        # notmuch abstraction (sole notmuch importer)
  models.py          # Domain dataclasses
  bundler.py         # Bundle rule matching (pure functions)
  composer.py        # Draft lifecycle
  sender.py          # Pipe to gmi send -t dispatch
  agent.py           # AI subprocess management
  actions/           # Action template engine
  tui/               # Textual screens and widgets
  ftux/              # First-time setup wizard
tests/               # pytest tests (mirror src/ structure)
docs/actions/        # Example action templates shipped with project
```

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->

## Running & Testing

```bash
# Install dependencies
uv sync

# Run TUI
uv run phr

# Run headless CLI
uv run phr status
uv run phr list --bundle=Newsletters

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/test_config.py -v

# Type checking
uv run mypy src/phyrax/
```

## Code Conventions

### Style

- Use Conventional Commits for all commit messages (e.g., `feat:`, `fix:`, `docs:`, `refactor:`).
- Use `ruff` for linting and formatting. Config is in `pyproject.toml`.
- Type hints on all public function signatures. Use `str | None` syntax (not `Optional`).
- Dataclasses for simple data containers. Pydantic models only for config (things that serialize to/from JSON).
- No `# type: ignore` without an adjacent comment explaining why.

### Imports

- `database.py` is the **sole** module that imports `notmuch2`. All other modules depend on the `Database` class and the dataclasses it returns (`ThreadSummary`, `MessageDetail`).
- No module imports an LLM SDK. AI interaction is always via `agent.py` subprocess calls.
- Use `from __future__ import annotations` in every module.

### Error Handling

- Raise domain-specific exceptions defined in `src/phyrax/exceptions.py`.
- Never catch bare `Exception`. Catch the narrowest type.
- Log errors via `logging.getLogger("phyrax")`. Log file: `~/.local/state/phyrax/phyrax.log`.

### Testing

- Every public function gets a test.
- Mock the AI agent subprocess — never call a real LLM in tests.
- Use a fixture Maildir (see `tests/conftest.py`) for database tests. **Never use a real mailbox** — not in tests, not in the harness, not anywhere.

#### TUI Testing Pyramid

There are two complementary layers for TUI testing. Both are mandatory.

**Layer 1 — Automated E2E (CI/CD assurance) via `pytest` + Textual Pilot:**

- Every new screen and every non-trivial widget must have an `async` test using `app.run_test()`.
- Tests simulate user flows via `await pilot.press("j", "enter")` and assert app state via `app.query_one(SomeWidget)`.
- Snapshot tests (`pytest-textual-snapshot`) catch visual regressions: use `assert_matches_snapshot(pilot)` to lock a known-good render. First run creates the snapshot; subsequent runs compare.
- Run the full suite: `uv run pytest tests/tui/ -v`

```python
async def test_inbox_renders(tmp_maildir, tmp_config_dir):
    async with PhyraxApp(...).run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        assert pilot.app.query_one(ThreadListWidget)
        await pilot.app.assert_matches_snapshot()
```

**Layer 2 — Interactive verification via `scripts/tui_harness.sh` (tmux bridge):**

The harness spawns the app in a detached tmux session against a synthetic fixture mailbox (with config pre-written to skip FTUX), then lets you send keystrokes and read the rendered terminal output.

```bash
./scripts/tui_harness.sh start          # start session with fixture mailbox
./scripts/tui_harness.sh keys j j Enter # navigate and press Enter
./scripts/tui_harness.sh read           # capture + print pane text
./scripts/tui_harness.sh stop           # kill session + clean up temp dir
```

**MANDATORY RULE:** Whenever you modify any file under `src/phyrax/tui/` or attempt to fix a UI bug, you MUST verify the fix interactively using `./scripts/tui_harness.sh` before marking the task complete. Run `start`, send the relevant keystrokes, run `read`, and include the captured pane output in your response as proof that the modal appeared, the text changed, or the layout did not crash.

**Pyramid Separation:**
- `pytest` + Pilot → automated, deterministic, runs in CI, no terminal needed
- `tui_harness.sh` → interactive, human-readable output, used during development and bug verification

## Key Architectural Rules

1. **Offline-first**: The TUI never opens a network socket. All reads/writes go to the local notmuch DB. `lieer` syncs asynchronously.

2. **Agent-agnostic AI**: AI is always an external subprocess. The command template is in `config.json` (`ai.agent_command`). Never import `anthropic`, `google.generativeai`, or any LLM library.

3. **notmuch is the single source of truth**: No shadow database, no SQLite cache, no JSON state files for email data. If it's not in notmuch, it doesn't exist.

4. **Prompt injection defense**: Every prompt sent to an AI agent uses XML boundaries. Email content is always inside `<email_payload>` with an explicit system instruction to treat it as inert data. See ARCHITECTURE.md §8.1.

5. **Config mutations are atomic**: `config.save()` writes to a temp file then renames. Never write config.json directly.

6. **PID lockfile**: Only one `phr` TUI instance at a time. Lockfile at `~/.cache/phyrax/phr.lock`. Check on startup, clean up on exit.

7. **Draft crash recovery**: Every draft is saved to `~/.cache/phyrax/drafts/{uuid}.txt` before opening $EDITOR. On startup, scan for orphaned drafts and prompt the user.

8. **Zero Framework Cognition (ZFC)**: Phyrax is a deterministic orchestrator. All reasoning, categorization, and intent-parsing must go through the external AI agent subprocess — never through in-process heuristics. Violations include regex/keyword guessing for semantic tasks (e.g., `if "newsletter" in subject`), keyword-scanning of agent stdout (e.g., `if "success" in output`), and hardcoded category lists substituting for LLM calls. Non-violations include matching user-authored `BundleRule` triples from `config.json`, parsing notmuch/MIME/date output, system-tag filtering, and exit-code branching on subprocess results.

## Implementation Sequence

Work through epics in this order (see `EPICS.md` for full issue breakdown):

1. **E0 — Project Scaffold**: pyproject.toml, directory structure, CI, ruff/mypy config
2. **E1 — Config & FTUX**: Pydantic models, load/save, first-run wizard
3. **E2 — Database Layer**: notmuch abstraction, query builder, fixture maildir
4. **E3 — Bundle Engine**: Rule matching, tag application, `f` feedback loop
5. **E4 — TUI Shell**: Textual App, InboxScreen, virtualized list, keybinding dispatch
6. **E5 — Thread View & Navigation**: ThreadViewScreen, BundleFocusScreen, CommandPalette
7. **E6 — AI Agent Integration**: Subprocess launcher, prompt compilation, context sanitization
8. **E7 — Compose & Send**: Draft lifecycle, $EDITOR integration, pandoc rendering, `gmi send` dispatch, Outbox manager
9. **E8 — Action Engine**: Template parser, execution pipeline, built-in task action
10. **E9 — Chat Interface**: The `?` key mailbox chat pane
11. **E10 — Headless CLI**: `phr status`, `phr list`, JSON output mode
12. **E11 — Polish & Packaging**: Error recovery, logging, man page, release packaging

## Things That Are NOT Phyrax's Responsibility

- **OAuth / credential management**: lieer handles this entirely.
- **Gmail API calls**: lieer handles sync. Phyrax only touches notmuch.
- **lieer installation or configuration**: Documented in README as a prerequisite.
- **notmuch initial setup**: Documented in README as a prerequisite (`notmuch new`).
- **AI agent installation**: The user installs their preferred agent CLI. Phyrax just calls it.
- **SMTP logic**: Phyrax simply pipes final MIME constructs directly to `gmi send -t`.
