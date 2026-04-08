# TUI Layer Rules

Actionable rules for all Textual screens and widgets.

## Subprocess Suspension

Before launching any interactive subprocess — including `$EDITOR`, the AI agent in interactive mode, or any process that needs a controlling terminal — call `App.suspend()`:

```python
with self.app.suspend():
    subprocess.run(["vim", str(draft_path)])
```

Never launch an interactive subprocess while the Textual event loop is running without suspending. Doing so corrupts terminal state.

## Keybindings Must Come from Config

All keybindings must be resolved from `config.keys` at runtime. No widget or screen may hardcode a key string.

```python
# Correct
archive_key = self.config.keys["archive"]  # e.g., "a"

# Wrong — hardcoded key
BINDINGS = [Binding("a", "archive", "Archive")]
```

The `config.keys` dict is the single source of truth for keybindings. Users change keys by editing `config.json`; the TUI picks them up on the next load.

## TUI Tests

Use Textual's `pilot` fixture via `app.run_test()` for all widget and screen tests:

```python
async def test_inbox_renders(app: PhyraxApp) -> None:
    async with app.run_test() as pilot:
        await pilot.press("q")
```

Never test TUI behavior by instantiating widgets outside a running `App`.

## ChatScreen Execution Model

`ChatScreen` uses a suspend-per-turn model. Each agent turn:

1. Suspend the TUI (`App.suspend()`).
2. Run the agent subprocess with inherited stdio so the user interacts directly with the agent's terminal UI.
3. Resume the TUI after the subprocess exits.

There is no in-TUI scrollback buffer for agent output. The agent manages its own display.

## Network Isolation

The TUI process must never open a network socket. All reads and writes go to the local notmuch database. `lieer` syncs asynchronously in a separate process.

Do not import `urllib`, `httpx`, `requests`, `aiohttp`, or any networking library in any TUI module.
