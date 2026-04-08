# Phyrax (`phr`)

A keyboard-first, AI-assisted terminal email client that syncs Gmail via `lieer`, indexes with `notmuch`, and orchestrates AI agents for drafting, triaging, and task extraction.

## Prerequisites

- Python ≥ 3.12
- [notmuch](https://notmuchmail.org/) ≥ 0.38
- [lieer](https://github.com/gauteh/lieer) ≥ 1.6 (`gmi`)
- [pandoc](https://pandoc.org/) ≥ 3.0
- An AI CLI agent: [Claude Code](https://claude.ai/code), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [Goose](https://github.com/block/goose), [OpenCode](https://opencode.ai/), or any custom command

## Installation

```bash
uv tool install phyrax
```

## First Run

```bash
# 1. Set up lieer (Gmail sync)
mkdir -p ~/mail && cd ~/mail
gmi init your@gmail.com && gmi sync

# 2. Set up notmuch
notmuch setup && notmuch new

# 3. Launch Phyrax — the first-run wizard handles the rest
phr
```

The first-run wizard asks which AI CLI you use, validates it's on your `$PATH`, then drops you into a chat session where the agent guides you through configuring bundles, aliases, and task actions.

## Usage

```bash
phr              # Launch TUI
phr status       # JSON inbox summary
phr list         # JSON thread list (default: inbox)
phr archive ID   # Archive a thread
phr tag ID +foo  # Tag operations
```

## Keybindings (defaults)

| Key | Action |
|---|---|
| `j`/`k` | Move cursor |
| `Enter` | Open thread / bundle |
| `a` | Archive |
| `r` | Reply |
| `f` | Feedback (AI bundle rule) |
| `t` | Task action |
| `Space` | Action menu |
| `o` | Outbox |
| `ctrl+p` | Command palette |
| `?` | AI chat |
| `q` | Quit |

See [ARCHITECTURE.md](ARCHITECTURE.md) for full technical documentation.
