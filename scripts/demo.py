#!/usr/bin/env python3
"""Launch Phyrax against a synthetic fixture mailbox for interactive testing.

Usage:
    uv run python scripts/demo.py

Creates a temp directory, populates it with 5 threads / 20 messages via
the test fixture generator, writes a minimal phyrax config, sets XDG env
vars so phyrax uses the temp dir, then execs 'phr'.

The temp directory is printed so you can inspect the maildir after exit.
Press Ctrl+C or 'q' inside phr to quit.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure src/ is on the path when running without 'uv run'
_repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(_repo_root / "src"))
sys.path.insert(0, str(_repo_root / "tests"))

from fixtures.maildir_builder import build_maildir


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="phyrax-demo-")
    root = Path(tmp)

    print(f"Demo directory: {root}")
    print("Building fixture mailbox (5 threads / 20 messages)…")

    fixture = build_maildir(root)

    print(f"  Maildir:        {fixture.maildir}")
    print(f"  NOTMUCH_CONFIG: {fixture.notmuch_config}")
    print(f"  Threads indexed: {len(fixture.thread_ids)}")

    # Minimal phyrax config — no AI agent (actions will notify gracefully)
    config_dir = root / "config" / "phyrax"
    config_dir.mkdir(parents=True)
    config = {
        "ai": {"agent_command": "echo"},
        "identity": {"primary": "demo@example.com", "aliases": []},
        "bundles": [
            {
                "name": "Newsletters",
                "label": "newsletters",
                "priority": 1,
                "rules": [
                    {"field": "from", "operator": "contains", "value": "substack.com"}
                ],
            },
            {
                "name": "Alerts",
                "label": "alerts",
                "priority": 2,
                "rules": [
                    {"field": "from", "operator": "contains", "value": "alerts@"}
                ],
            },
        ],
        "task": {"action": None},
        "compose": {"include_quote": True},
        "keys": {
            "archive": "a",
            "reply": "r",
            "task": "t",
            "feedback": "f",
            "outbox": "o",
            "chat": "question_mark",
        },
    }
    (config_dir / "config.json").write_text(json.dumps(config, indent=2))

    # Set XDG dirs so phyrax uses the temp tree
    env = os.environ.copy()
    env["NOTMUCH_CONFIG"] = str(fixture.notmuch_config)
    env["XDG_CONFIG_HOME"] = str(root / "config")
    env["XDG_CACHE_HOME"] = str(root / "cache")
    env["XDG_STATE_HOME"] = str(root / "state")
    env["PHYRAX_LOG_LEVEL"] = "DEBUG"

    print()
    print("Starting phr… (press 'q' to quit)")
    print()

    # Exec phr directly — replaces this process
    phr = _repo_root / ".venv" / "bin" / "phr"
    if not phr.exists():
        # Fall back to PATH
        import shutil
        found = shutil.which("phr")
        if found:
            phr = Path(found)
        else:
            print("ERROR: 'phr' not found. Run 'uv sync' first.", file=sys.stderr)
            sys.exit(1)

    os.execve(str(phr), [str(phr)], env)


if __name__ == "__main__":
    main()
