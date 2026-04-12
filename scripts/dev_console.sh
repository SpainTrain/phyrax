#!/usr/bin/env bash
# dev_console.sh — Open the Textual devtools console.
#
# Usage:
#   ./scripts/dev_console.sh
#
# Run this in a second terminal alongside scripts/dev.sh to observe
# widget events, reactive changes, and self.log() output.
# Pass args to filter groups, e.g.: ./scripts/dev_console.sh -x SYSTEM -x EVENT

exec uv run textual console "$@"
