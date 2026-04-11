#!/usr/bin/env bash
# _fixture_env.sh — Build a synthetic fixture mailbox and print env var lines.
#
# Usage (sourced by tui_harness.sh):
#   eval "$( REPO_ROOT="$REPO_ROOT" "$REPO_ROOT/scripts/_fixture_env.sh" )"
#
# Environment variables:
#   REPO_ROOT  Absolute path to the repository root (required).
#
# Prints KEY=VALUE lines to stdout for:
#   HARNESS_TMP, NOTMUCH_CONFIG, XDG_CONFIG_HOME, XDG_CACHE_HOME, XDG_STATE_HOME

set -euo pipefail

: "${REPO_ROOT:?REPO_ROOT must be set}"

python3 - <<'PYEOF'
import json
import os
import sys
import tempfile
from pathlib import Path

repo_root = Path(os.environ["REPO_ROOT"])
sys.path.insert(0, str(repo_root / "tests"))

from fixtures.maildir_builder import build_maildir

tmp = tempfile.mkdtemp(prefix="phyrax-harness-")
root = Path(tmp)

fixture = build_maildir(root)

# Write minimal config to skip FTUX
config_dir = root / "config" / "phyrax"
config_dir.mkdir(parents=True)
config = {
    "identity": {"primary": "test@example.com", "aliases": []},
    "ai": {"agent_command": "echo"},
    "bundles": [
        {
            "name": "Alerts",
            "label": "alerts",
            "priority": 1,
            "rules": [{"field": "from", "operator": "contains", "value": "alerts@"}],
        },
        {
            "name": "Newsletters",
            "label": "newsletters",
            "priority": 2,
            "rules": [{"field": "from", "operator": "contains", "value": "substack.com"}],
        },
    ],
    "compose": {"include_quote": True},
    "task": {"action": None},
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

print(f"HARNESS_TMP={tmp}")
print(f"NOTMUCH_CONFIG={fixture.notmuch_config}")
print(f"XDG_CONFIG_HOME={root / 'config'}")
print(f"XDG_CACHE_HOME={root / 'cache'}")
print(f"XDG_STATE_HOME={root / 'state'}")
PYEOF
