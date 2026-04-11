# Phyrax (`phr`)

> A keyboard-first, AI-assisted terminal email client for Gmail power users.

## What Phyrax Is (and Isn't)

Phyrax is a TUI and headless CLI that sits on top of `notmuch` and `lieer`. It bundles threads
by rule, drafts replies through your `$EDITOR`, and orchestrates an AI CLI agent for triage,
task extraction, and mailbox chat.

**Phyrax is NOT responsible for:**

- OAuth / credential management — `lieer` handles this entirely.
- Gmail API calls — `lieer` syncs your mail; Phyrax only reads and writes the local notmuch database.
- SMTP — Phyrax pipes the final MIME message directly to `gmi send -t`.
- AI agent installation — you install your preferred agent CLI; Phyrax invokes it as a subprocess.
- notmuch initial setup — documented below as a prerequisite.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical specification.

## Prerequisites

- **Python** >= 3.12
- **[notmuch](https://notmuchmail.org/)** >= 0.38 — email index
- **[lieer](https://github.com/gauteh/lieer)** >= 1.6 (`gmi`) — Gmail sync
- **[pandoc](https://pandoc.org/)** >= 3.0 — Markdown to HTML for outbound email
- **An AI CLI agent** — [Claude Code](https://claude.ai/code), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [Goose](https://github.com/block/goose), [OpenCode](https://opencode.ai/), or any command that accepts a prompt string as an argument

## Installation

```bash
uv tool install phyrax
```

## First Run

```bash
# 1. Set up lieer in a Maildir directory
mkdir -p ~/mail && cd ~/mail
gmi init your@gmail.com && gmi sync

# 2. Initialize notmuch
notmuch setup && notmuch new

# 3. Launch Phyrax — the FTUX wizard handles the rest
phr
```

The first-time setup wizard asks which AI CLI you use, validates it is on your `$PATH`, and
drops you into a guided chat session where the agent helps you configure bundles, email aliases,
and task actions.

## Usage

```bash
phr              # Launch TUI
phr status       # Print inbox summary as JSON
phr list         # Print thread list as JSON (default: inbox)
phr list --bundle=Newsletters
phr archive ID   # Archive a thread
phr tag ID +foo  # Add / remove notmuch tags
```

## Keybindings

These are the defaults. All keys are configurable via `config.json` (`config.keys`).

| Key | Action |
|-----|--------|
| `j` / `k` | Move cursor down / up |
| `Enter` | Open thread or expand bundle |
| `a` | Archive thread (or entire bundle when on bundle header) |
| `r` | Reply — opens compose modal |
| `f` | Feedback — flag a miscategorized thread to improve bundle rules |
| `t` | Run task action on thread |
| `Space` | Open action menu |
| `o` | Open outbox |
| `ctrl+p` | Command palette |
| `?` | Open AI mailbox chat |
| `q` | Quit |

## Development

```bash
# Install dependencies
uv sync

# Try the app safely (fixture mailbox, no real email touched)
uv run phr --demo

# Run the real TUI (requires notmuch + lieer set up)
uv run phr

# Run tests
uv run pytest

# Lint, format, type-check
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
uv run mypy src/phyrax/
```

`phr --demo` creates an isolated temp directory with synthetic emails and runs the full FTUX wizard — safe for iterating on the TUI without touching your real mailbox.

## Further Reading

- [ARCHITECTURE.md](ARCHITECTURE.md) — system design, data flow, agent security model
- [EPICS.md](EPICS.md) — feature roadmap and issue breakdown
- [docs/actions/](docs/actions/) — example action templates
