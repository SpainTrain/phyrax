# EPICS.md — Phyrax Implementation Plan

Each issue is sized for a single focused session. Dependencies are explicit — never start an issue before its dependencies are done.

---

## E0 — Project Scaffold

### E0-1: Initialize repository and pyproject.toml
**Files**: `pyproject.toml`, `README.md`, `src/phyrax/__init__.py`
**Acceptance Criteria**:
- `pyproject.toml` uses hatchling build backend
- `requires-python = ">=3.12"`
- Dependencies: textual, typer, notmuch2, pydantic, platformdirs
- Dev dependencies: pytest, pytest-textual-snapshot, mypy, ruff
- `[project.scripts]` maps `phr = "phyrax.cli:app"`
- `uv sync` succeeds
- `uv run phr --help` prints a stub help message

### E0-2: Configure ruff, mypy, and pre-commit
**Depends on**: E0-1
**Files**: `pyproject.toml` (tool sections), `.pre-commit-config.yaml`
**Acceptance Criteria**:
- ruff configured: line-length 100, isort, pyflakes, pycodestyle
- mypy configured: strict mode, explicit-package-bases
- `uv run ruff check src/` passes on empty project
- `uv run mypy src/phyrax/` passes on empty project

### E0-3: Create directory skeleton and stub modules
**Depends on**: E0-1
**Files**: All `__init__.py` files, stub `.py` files for every module in ARCHITECTURE.md §3
**Acceptance Criteria**:
- Every module listed in ARCHITECTURE.md exists as a file with a module docstring
- Every public class/function from ARCHITECTURE.md §6 exists as a stub (raises `NotImplementedError`)
- `uv run mypy src/phyrax/` still passes
- `src/phyrax/exceptions.py` created with base `PhyraxError` and subclasses: `ConfigError`, `DatabaseError`, `AgentError`, `ComposeError`, `SendError`

### E0-4: Create test skeleton and fixture infrastructure
**Depends on**: E0-3
**Files**: `tests/conftest.py`, `tests/test_*.py` stubs
**Acceptance Criteria**:
- `tests/conftest.py` contains pytest fixtures:
  - `tmp_config_dir`: temp directory with a valid `config.json`
  - `tmp_maildir`: temp directory with a synthetic Maildir (~20 messages, 5 threads, varying tags)
  - `mock_agent_command`: path to a shell script that echoes its input
- One placeholder test per test file that passes
- `uv run pytest` passes with all placeholders

---

## E1 — Config & FTUX

### E1-1: Implement PhyraxConfig Pydantic models
**Depends on**: E0-3
**Files**: `src/phyrax/config.py`
**Acceptance Criteria**:
- All models from ARCHITECTURE.md §6.2 implemented
- `PhyraxConfig.load()` reads from disk, returns defaults if file missing
- `PhyraxConfig.save()` writes atomically (write to `.tmp`, then `os.rename`)
- `is_first_run` property works
- Path constants (CONFIG_DIR, DRAFTS_DIR, etc.) use platformdirs

### E1-2: Write config tests
**Depends on**: E1-1, E0-4
**Files**: `tests/test_config.py`
**Acceptance Criteria**:
- Test load from valid JSON
- Test load with missing file returns defaults
- Test load with partial JSON (missing keys filled with defaults)
- Test load with invalid JSON raises `ConfigError`
- Test save + reload roundtrip
- Test atomic save (simulate crash mid-write doesn't corrupt)
- Test `is_first_run` true/false
- Test BundleRule validation (operator "exists" requires value=None)

### E1-3: Implement FTUX AI setup wizard
**Depends on**: E1-1
**Files**: `src/phyrax/ftux/wizard.py`
**Acceptance Criteria**:
- `run_ai_setup_wizard()` presents a Textual selection screen with presets:
  - Claude Code (`claude -p %s`)
  - Gemini CLI (`gemini --input %s`)
  - Goose (`goose run --prompt-file %s`)
  - OpenCode (`opencode --file %s`)
  - Custom (free text input)
- Selected command is validated: check if the binary exists on `$PATH` via `shutil.which()`
- If binary not found, show warning and allow user to proceed anyway or re-select
- Returns populated `AIConfig`

### E1-4: Implement FTUX task setup wizard
**Depends on**: E1-1
**Files**: `src/phyrax/ftux/wizard.py`
**Acceptance Criteria**:
- `run_task_setup_wizard()` presents options:
  - "I'll configure this later" (sets `task.action = null`, wizard exits)
  - "Create from preset" (shows list: Obsidian, TickTick, Todoist, Linear, custom)
  - Each preset writes a corresponding `.md` action template to `ACTIONS_DIR`
- Returns populated `TaskConfig` with the action template filename

### E1-5: Write FTUX tests
**Depends on**: E1-3, E1-4
**Files**: `tests/test_ftux.py`
**Acceptance Criteria**:
- Test AI wizard with valid command on PATH → returns AIConfig
- Test AI wizard with missing binary → warning shown
- Test task wizard "configure later" → TaskConfig.action is None
- Test task wizard preset selection → action template file created on disk
- All tests use Textual pilot for screen interaction

---

## E2 — Database Layer

### E2-1: Implement Database class
**Depends on**: E0-3
**Files**: `src/phyrax/database.py`, `src/phyrax/models.py`
**Acceptance Criteria**:
- `Database.__init__` opens notmuch DB (auto-detect path from notmuch config, or accept explicit path)
- `query_threads()` returns `list[ThreadSummary]` with offset/limit support
- `count_threads()` returns int (fast Xapian count)
- `get_thread_messages()` returns `list[MessageDetail]` ordered chronologically
- `add_tags()` and `remove_tags()` work on all messages in a thread
- `gmail_thread_id` extracted from `X-GM-THRID` header
- `snippet` extracted from newest message's text/plain body (first 200 chars)
- `AttachmentMeta` populated from MIME parts (content not loaded)
- `get_attachment_content()` extracts bytes from the MIME tree

### E2-2: Write database tests
**Depends on**: E2-1, E0-4
**Files**: `tests/test_database.py`
**Acceptance Criteria**:
- Uses `tmp_maildir` fixture with pre-built notmuch database
- Test `query_threads("tag:inbox")` returns expected threads
- Test `count_threads` matches `len(query_threads)` for same query
- Test `query_threads` with offset/limit pagination
- Test `get_thread_messages` returns correct message order
- Test `add_tags` / `remove_tags` persists and re-query reflects change
- Test query with nonexistent tag returns empty list
- Test `get_attachment_content` returns correct bytes for a fixture attachment

### E2-3: Build synthetic Maildir fixture generator
**Depends on**: E0-4
**Files**: `tests/conftest.py` (expand `tmp_maildir` fixture)
**Acceptance Criteria**:
- Generates a valid Maildir with:
  - 5 threads, 2-5 messages each (20 messages total)
  - Thread 1: 3 messages from `alerts@example.com` (matches Alerts bundle)
  - Thread 2: 2 messages from `newsletter@substack.com` (matches Newsletters bundle)
  - Thread 3: 4 messages from `boss@company.com` (direct, high-priority)
  - Thread 4: 1 message with a PDF attachment
  - Thread 5: 3 messages in a reply chain with quoted text
- Each message has `X-GM-THRID` header
- `notmuch new` runs on the fixture to build the Xapian index
- Tags pre-applied: `inbox`, `unread` on all; `alerts` on thread 1; `newsletters` on thread 2

---

## E3 — Bundle Engine

### E3-1: Implement bundle rule matching
**Depends on**: E2-1
**Files**: `src/phyrax/bundler.py`
**Acceptance Criteria**:
- `match_thread_to_bundle()` evaluates rules top-down, first match wins
- Supports operators: `contains` (case-insensitive substring), `equals` (exact), `matches` (regex), `exists` (header present)
- `field` supports: `from`, `to`, `subject`, `header:<name>` (arbitrary header lookup)
- Returns `None` if no bundle matches
- `apply_bundle_tags()` adds the bundle's label tag to the thread (idempotent)

### E3-2: Write bundler tests
**Depends on**: E3-1, E2-3
**Files**: `tests/test_bundler.py`
**Acceptance Criteria**:
- Test `contains` operator on `from` field
- Test `equals` operator (case-sensitive)
- Test `matches` operator with regex
- Test `exists` operator on `header:List-Id`
- Test first-match-wins when multiple bundles could match
- Test no match returns None
- Test `apply_bundle_tags` adds tag, re-query shows tag, second call is no-op

### E3-3: Implement feedback loop (rule generation)
**Depends on**: E3-1, E6-1
**Files**: `src/phyrax/bundler.py` (add `generate_bundle_rule` function)
**Acceptance Criteria**:
- `generate_bundle_rule(message, user_description, config)` calls AI agent in captured mode
- Prompt instructs AI to output a JSON `BundleRule` based on the message headers and user's description
- Parses AI response into a `BundleRule`, validates it
- Appends rule to the matching bundle (or creates a new bundle) in config
- Calls `config.save()`
- If AI output is unparseable, raises `AgentError` with the raw output for debugging

---

## E4 — TUI Shell

### E4-1: Implement PhyraxApp and InboxScreen
**Depends on**: E1-1, E2-1
**Files**: `src/phyrax/app.py`, `src/phyrax/tui/screens/inbox.py`
**Acceptance Criteria**:
- `PhyraxApp` subclasses `textual.App`
- On mount: checks PID lockfile (create or error), loads config, opens DB
- If `config.is_first_run`, pushes FTUX wizard screens first
- InboxScreen is the default screen
- Shows a placeholder thread list (can be static for now, virtualization in E4-2)
- StatusBar widget at bottom shows: unread count, sync status placeholder, current screen name
- `q` quits from InboxScreen

### E4-2: Implement virtualized ThreadListWidget
**Depends on**: E4-1
**Files**: `src/phyrax/tui/widgets/thread_list.py`
**Acceptance Criteria**:
- Extends Textual's virtualized list pattern
- Queries notmuch via `Database.query_threads()` with rolling window (viewport_height * 3)
- Each row displays: sender (truncated), subject, relative date, unread indicator, tag pills
- `j`/`k` or arrow keys move cursor
- Cursor wraps at boundaries (or stops — pick one, document in code)
- Bundles render as collapsible group headers with thread count and bundle name
- Threads within a bundle are grouped under their bundle header
- Unbundled threads (no matching bundle) appear at the top, sorted by date

### E4-3: Implement keybinding dispatch
**Depends on**: E4-2
**Files**: `src/phyrax/tui/screens/inbox.py`
**Acceptance Criteria**:
- Keybindings read from `config.keys` (not hardcoded strings)
- `a` on a thread: calls `Database.remove_tags(thread_id, ["inbox"])`, refreshes list
- `a` on a bundle header: archives all threads in that bundle
- `Enter` on a bundle header: pushes BundleFocusScreen
- `Enter` on a thread: pushes ThreadViewScreen
- `f` on a thread: opens feedback flow
- `t` on a thread: triggers task action
- `Space` on a thread: opens ActionMenu
- `o` on any screen: opens OutboxScreen
- `ctrl+p`: opens CommandPalette
- `?`: opens ChatScreen

### E4-4: Write TUI shell tests
**Depends on**: E4-3
**Files**: `tests/tui/test_inbox_screen.py`
**Acceptance Criteria**:
- Uses Textual pilot with `tmp_maildir` fixture
- Test app launches without error
- Test inbox shows expected thread count
- Test `a` key removes thread from inbox view
- Test `q` key exits app
- Test PID lockfile created on launch, removed on exit
- Test second instance errors on lockfile conflict

---

## E5 — Thread View & Navigation

### E5-1: Implement ThreadViewScreen
**Depends on**: E4-1, E2-1
**Files**: `src/phyrax/tui/screens/thread_view.py`
**Acceptance Criteria**:
- Pushed when user presses Enter on a thread
- Displays all messages in the thread chronologically
- Each message shows: from, to, cc, date, subject (if differs from thread), body (text/plain)
- Scrollable if thread is long
- `Escape` pops back to previous screen
- `ctrl+g` constructs Gmail URL from `gmail_thread_id` and calls `open <url>`
- `r` key opens ComposeModal
- Attachment list shown per message (filename, type, size — no download yet)

### E5-2: Implement BundleFocusScreen
**Depends on**: E4-1, E4-2
**Files**: `src/phyrax/tui/screens/bundle_focus.py`
**Acceptance Criteria**:
- Pushed when user presses Enter on a bundle header in InboxScreen
- Reuses `ThreadListWidget` with a filtered query: `tag:{bundle_label} AND tag:inbox`
- Title bar shows bundle name
- All keybindings work identically to InboxScreen within the filtered context
- `Escape` pops back to InboxScreen
- `a` on the entire view archives the whole bundle

### E5-3: Implement CommandPalette
**Depends on**: E4-1
**Files**: `src/phyrax/tui/widgets/command_palette.py`
**Acceptance Criteria**:
- Opened by `ctrl+p`, renders as a centered overlay
- Fuzzy-search text input at top
- Entries include:
  - All bundle names → navigates to BundleFocusScreen for that bundle
  - "[Outbox]" → navigates to OutboxScreen
  - "All Mail" → query `*`
  - "Starred" → query `tag:flagged`
  - "Sent" → query `tag:sent`
  - "Settings" → opens config.json in $EDITOR (suspend TUI)
- Enter selects, Escape closes
- Results filter as user types (substring match on entry name)

### E5-4: Write navigation tests
**Depends on**: E5-1, E5-2, E5-3
**Files**: `tests/tui/test_thread_view.py`, `tests/tui/test_navigation.py`
**Acceptance Criteria**:
- Test Enter on thread → ThreadViewScreen pushed, shows correct messages
- Test Escape from ThreadViewScreen → back to InboxScreen
- Test Enter on bundle → BundleFocusScreen pushed with filtered threads
- Test ctrl+p opens CommandPalette, typing filters, Enter navigates
- Test ctrl+g constructs correct Gmail URL (mock `subprocess.run` for `open`)

---

## E6 — AI Agent Integration

### E6-1: Implement agent.py (prompt compilation + subprocess)
**Depends on**: E1-1
**Files**: `src/phyrax/agent.py`
**Acceptance Criteria**:
- `compile_prompt()` writes structured XML prompt to a temp file, returns path
- XML structure matches ARCHITECTURE.md §8.1 exactly
- Base64 stripping: all base64 MIME parts replaced with `<attachment ... action="stripped_by_phyrax" />`
- Quote trimming: lines starting with `>` removed; only newest 2-3 messages retained
- Header filtering: only From, To, Cc, Date, Subject, Message-ID included
- `require_full_context=True` disables quote trimming
- `allow_attachments=True` retains supported attachments
- `run_agent()` in captured mode: runs subprocess, captures stdout/stderr, returns `AgentResult`
- `run_agent_interactive()`: runs subprocess with inherited stdio, returns exit code
- Fallback: if primary exits non-zero and `fallback_command` set, retry with fallback
- `%s` in agent_command is replaced with the prompt file path

### E6-2: Write agent tests
**Depends on**: E6-1, E0-4
**Files**: `tests/test_agent.py`
**Acceptance Criteria**:
- Test `compile_prompt` output contains XML boundaries in correct structure
- Test base64 stripping replaces base64 content with placeholder
- Test quote trimming removes `>` lines
- Test `require_full_context=True` retains quotes
- Test `allow_attachments=True` retains attachment data
- Test `run_agent` captured mode with mock echo command
- Test `run_agent` fallback on primary failure
- Test `run_agent` with no fallback on primary failure raises `AgentError`
- Test `%s` replacement in command template

---

## E7 — Compose & Send

### E7-1: Implement ComposeModal (intent capture)
**Depends on**: E5-1
**Files**: `src/phyrax/tui/screens/compose.py`
**Acceptance Criteria**:
- Modal screen pushed by `r` key from ThreadViewScreen or InboxScreen
- Shows: "Replying to: {subject}" and "From: {sender}"
- Text input: "AI Instructions (leave blank for manual draft):"
- Enter submits, Escape cancels
- On submit with instructions: triggers AI draft generation flow
- On submit with blank: drops directly to draft pipeline with empty body

### E7-2: Implement draft lifecycle
**Depends on**: E7-1, E6-1
**Files**: `src/phyrax/composer.py`
**Acceptance Criteria**:
- `generate_draft()` calls agent in captured mode with reply context + user instructions
- Creates `Draft` dataclass with uuid, metadata, body
- `save_draft()` writes to `~/.cache/phyrax/drafts/{uuid}.txt`
- Draft file format: standard email headers (To, Cc, Subject, In-Reply-To) generated at the top + Markdown body below
- `open_editor()` suspends TUI, opens `$EDITOR` on the draft file, reads back on exit
- Parses file on return to split manually edited headers from Markdown body
- `recover_unsent_drafts()` scans drafts dir, parses each file, returns list
- `cleanup_draft()` deletes the file

### E7-3: Implement send pipeline (MIME + gmi dispatch)
**Depends on**: E7-2
**Files**: `src/phyrax/sender.py`
**Acceptance Criteria**:
- `render_html()` invokes `pandoc` to convert parsed Markdown body → HTML
- `send_reply()` constructs multipart/alternative MIME (text/plain + text/html)
- Applies parsed routing headers to the MIME object
- Dispatches by piping the raw MIME string directly to `subprocess.run(["gmi", "send", "-t"])`
- `preview_in_browser()` writes HTML to temp file, calls `open <path>`
- After successful send: call `cleanup_draft()` (`lieer` handles +sent tagging natively)

### E7-4: Implement OutboxScreen (Draft Staging)
**Depends on**: E7-2, E7-3
**Files**: `src/phyrax/tui/screens/outbox.py`
**Acceptance Criteria**:
- Triggered by `o` key or Command Palette.
- Reads `~/.cache/phyrax/drafts/` and displays queued `.txt` files in a table
- Pressing `Enter` opens a slide-over Preview Pane showing the Markdown body and locked headers
- Draft Actions:
  - `e`: Suspends TUI, opens `$EDITOR` for the selected draft
  - `p`: Renders HTML and opens browser preview
  - `d`: Prompts "Discard draft? [Y/n]", deletes file if confirmed
  - `s`: Prompts "Dispatch email to [Recipient]? (y/N)". On confirm, triggers `send_reply()`

### E7-5: Wire compose flow end-to-end in TUI
**Depends on**: E7-1, E7-4
**Files**: `src/phyrax/tui/screens/thread_view.py`, `src/phyrax/tui/screens/inbox.py`
**Acceptance Criteria**:
- `r` → ComposeModal → (AI draft or blank) → generates headers & writes `.txt` → $EDITOR → TUI resumes
- After $EDITOR exits: Draft saved to cache. Status bar flashes: "Draft saved. Press 'o' for Outbox."
- On startup: if orphaned drafts found, show "N unsent drafts in Outbox." notification

### E7-6: Write compose and send tests
**Depends on**: E7-4, E7-5
**Files**: `tests/test_composer.py`, `tests/test_sender.py`
**Acceptance Criteria**:
- Test `generate_draft` with mock agent returns valid Draft
- Test `save_draft` prepends headers + recovers correctly
- Test parsed headers update Draft state
- Test `render_html` produces valid HTML
- Test MIME construction: multipart/alternative with correct parts
- Test `gmi send -t` subprocess is called correctly with piped MIME input
- Test `cleanup_draft` deletes file

---

## E8 — Action Engine

### E8-1: Implement action template parser
**Depends on**: E1-1
**Files**: `src/phyrax/actions/engine.py`
**Acceptance Criteria**:
- `list_actions()` scans `ACTIONS_DIR` for `*.md` files
- Parses YAML frontmatter: `name`, `description`, `require_full_context` (default false), `allow_attachments` (default false)
- Remaining Markdown content is the `prompt_body`
- Returns `list[ActionTemplate]`
- Gracefully handles malformed files (log warning, skip)

### E8-2: Implement action execution pipeline
**Depends on**: E8-1, E6-1
**Files**: `src/phyrax/actions/engine.py`
**Acceptance Criteria**:
- `execute_action()` compiles prompt using `agent.compile_prompt()` with the action's flags
- Prompt body from the action template is placed in `<user_prompt>`
- Email payload from the selected message is placed in `<email_payload>`
- Launches agent interactively (caller must suspend TUI)
- Returns exit code from agent

### E8-3: Implement ActionMenu widget
**Depends on**: E8-1
**Files**: `src/phyrax/tui/widgets/action_menu.py`
**Acceptance Criteria**:
- Overlay triggered by Space key when a thread is highlighted
- Lists all actions from `list_actions()`: name and description
- Arrow keys to navigate, Enter to select, Escape to cancel
- On select: suspends TUI, calls `execute_action()`, resumes TUI

### E8-4: Implement built-in task action
**Depends on**: E8-2, E1-4
**Files**: `src/phyrax/actions/builtins.py`
**Acceptance Criteria**:
- `t` key triggers: if `config.task.action` is None, run task setup wizard (E1-4)
- If `config.task.action` is set, execute that action template interactively
- After successful execution, tag thread `+task-created`

### E8-5: Write action engine tests
**Depends on**: E8-1, E8-2
**Files**: `tests/test_actions.py`
**Acceptance Criteria**:
- Test `list_actions` with 0, 1, 3 action files
- Test parser handles missing optional frontmatter fields
- Test `execute_action` compiles correct prompt structure
- Test `execute_action` passes correct flags to `compile_prompt`

---

## E9 — Chat Interface

### E9-1: Implement ChatScreen
**Depends on**: E6-1, E2-1
**Files**: `src/phyrax/tui/screens/chat.py`
**Acceptance Criteria**:
- Pushed by `?` key from any screen
- Split layout: scrollable message history (top), text input (bottom)
- User types a question, presses Enter
- App compiles a prompt with the user's question + a system preamble
- Agent runs in captured mode; response displayed in the chat history
- Context includes: summary of current inbox state (unread count, top bundles)
- `Escape` closes chat and returns to previous screen

### E9-2: Write chat tests
**Depends on**: E9-1
**Files**: `tests/tui/test_chat.py`
**Acceptance Criteria**:
- Test `?` opens ChatScreen
- Test typing message triggers agent call
- Test agent response appears in chat history

---

## E10 — Headless CLI

### E10-1: Implement `phr status` command
**Depends on**: E2-1, E1-1
**Files**: `src/phyrax/cli.py`
**Acceptance Criteria**:
- `phr status` outputs JSON:
  ```json
  {
    "inbox_total": 42,
    "inbox_unread": 7,
    "bundles": [
      {"name": "Newsletters", "count": 12, "unread": 3}
    ],
    "unbundled": 25,
    "drafts_pending": 0
  }
  ```
- Exits 0 on success
- Does NOT acquire PID lockfile (read-only operation)

### E10-2: Implement `phr list` command
**Depends on**: E2-1
**Files**: `src/phyrax/cli.py`
**Acceptance Criteria**:
- `phr list` outputs JSON array of threads (default: inbox)
- `phr list --bundle=Newsletters` filters to bundle
- `phr list --query="from:boss@company.com"` passes raw notmuch query
- Each thread in output: `thread_id`, `subject`, `authors`, `date`, `tags`, `snippet`

### E10-3: Implement `phr archive` and `phr tag` commands
**Depends on**: E2-1
**Files**: `src/phyrax/cli.py`
**Acceptance Criteria**:
- `phr archive <thread_id>` removes `inbox` tag
- `phr tag <thread_id> +foo -bar` adds/removes tags
- Outputs JSON confirmation

### E10-4: Write CLI tests
**Depends on**: E10-1, E10-2, E10-3
**Files**: `tests/test_cli.py`
**Acceptance Criteria**:
- Test `phr status` JSON schema
- Test `phr list` default and with filters
- Test `phr archive` removes inbox tag

---

## E11 — Polish & Packaging

### E11-1: Implement structured logging
**Depends on**: E4-1
**Files**: `src/phyrax/logging.py`, modifications to all modules
**Acceptance Criteria**:
- `setup_logging()` called once at startup
- Logs to `~/.local/state/phyrax/phyrax.log`

### E11-2: Implement error recovery flows
**Depends on**: E7-4, E4-1
**Files**: `src/phyrax/app.py`
**Acceptance Criteria**:
- Stale PID lockfile detection and cleanup
- Draft crash recovery prompt on startup
- DB lock retry with backoff (3 attempts, ~500ms)

### E11-3: Write README with setup instructions
**Depends on**: E10-1
**Files**: `README.md`
**Acceptance Criteria**:
- Prerequisites: Python 3.12+, notmuch, lieer, pandoc, an AI CLI agent
- Installation: `uv tool install phyrax`

### E11-4: Package for distribution
**Depends on**: E11-3
**Files**: `pyproject.toml` (metadata), `LICENSE`
**Acceptance Criteria**:
- `uv build` produces wheel and sdist

### E11-5: ZFC Guardrails & Audit
**Depends on**: E6-1, E8-2, E3-3
**Files**: `CLAUDE.md`, `src/phyrax/bundler.py`, `src/phyrax/actions/engine.py`, `src/phyrax/agent.py`, `tests/test_agent.py`
**Acceptance Criteria**:
- ZFC (Zero Framework Cognition) rule documented in `CLAUDE.md`: Phyrax is a deterministic orchestrator; all reasoning must go through the external AI agent subprocess; client-side heuristics (regex guessing, keyword lists, string-matching agent output) are prohibited violations (done via phyrax-x9s)
- Audit `bundler.py` for client-side heuristics: any pattern-matching or inference that should be delegated to the agent subprocess is removed or replaced with agent calls
- Audit `actions/engine.py` for client-side heuristics: template selection logic must not guess intent; the agent decides
- All structured agent outputs (e.g., `BundleRule` JSON from `generate_bundle_rule()`) are validated via Pydantic schema immediately after parsing; raw agent output that fails schema validation raises `AgentError` with the raw output included
- Regression test in `tests/test_agent.py`: `run_agent()` in captured mode raises `AgentError` (not silently returns) when the agent subprocess produces unstructured output where structured output is required
