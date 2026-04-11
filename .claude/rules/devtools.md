# Textual Devtools Rules

Actionable rules for using `textual-dev` during TUI development.

## CSS Lives in .tcss Files

Never write CSS inside Python source. Do not use `DEFAULT_CSS` or `CSS` class attributes with string literals in any `App`, `Screen`, or `Widget` subclass.

```python
# Wrong — inline CSS string
class InboxScreen(Screen):
    CSS = """
    ListView { height: 1fr; }
    """

# Correct — reference a sibling .tcss file
class InboxScreen(Screen):
    CSS_PATH = "inbox.tcss"
```

All styles live in `.tcss` files co-located with their corresponding Python module. This is required for `textual run --dev` hot-reload to work. Hot-reload does not watch Python source files; only `.tcss` files are reloaded on change.

## Dev Launcher

Use `scripts/dev.sh` when iterating on CSS or widget layout. Never use `uv run phr` for live CSS development.

```bash
# Correct — enables CSS hot-reload via textual-dev
bash scripts/dev.sh        # wraps: textual run --dev src/phyrax/app.py

# Wrong — production entry point, no hot-reload
uv run phr
```

`uv run phr` is for end-to-end and production smoke tests only. It does not load the Textual devtools server and will not reflect `.tcss` changes without a full restart.

## Devtools Console

Use `scripts/dev_console.sh` in a second terminal to observe widget events and `log()` output during a dev session.

```bash
# Terminal 1: run the app with devtools enabled
bash scripts/dev.sh

# Terminal 2: open the devtools console
bash scripts/dev_console.sh    # wraps: textual console
```

Always open the console before starting a layout debugging session. Widget mount/unmount events, reactive changes, and `self.log(...)` calls are only visible in the console, not in the app terminal.

## Harness for Non-CSS Bugs

For logic, navigation, or keybinding bugs that do not involve CSS changes, use `scripts/tui_harness.sh` (the tmux bridge) instead of `textual run --dev`.

```bash
# Correct for logic/navigation debugging
bash scripts/tui_harness.sh

# Wrong for logic bugs — --dev overhead is unnecessary and may mask timing issues
bash scripts/dev.sh
```

`textual run --dev` injects the devtools server into the event loop. Use it only when you need hot-reload or the devtools console; otherwise use the harness.

## Snapshot Refresh After CSS Changes

After any `.tcss` change, regenerate the SVG snapshot baselines before committing:

```bash
uv run pytest tests/tui/test_e2e_inbox.py --snapshot-update
```

Never commit a `.tcss` change without also committing the updated snapshot files. A stale snapshot will cause CI to fail on the first run after the CSS change.
