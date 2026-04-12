#!/usr/bin/env bash
# dev.sh — start phr in Textual dev mode against a fixture mailbox.
# Live CSS reload and devtools console protocol are enabled.
# Pair with: ./scripts/dev_console.sh in a second terminal.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

eval "$(REPO_ROOT="$REPO_ROOT" "$REPO_ROOT/scripts/_fixture_env.sh")"

cleanup() {
    if [[ -n "${HARNESS_TMP:-}" && -d "$HARNESS_TMP" ]]; then
        rm -rf "$HARNESS_TMP"
    fi
}
trap cleanup EXIT INT TERM

NOTMUCH_CONFIG="$NOTMUCH_CONFIG" \
XDG_CONFIG_HOME="$XDG_CONFIG_HOME" \
XDG_CACHE_HOME="$XDG_CACHE_HOME" \
XDG_STATE_HOME="$XDG_STATE_HOME" \
PHYRAX_LOG_LEVEL=DEBUG \
uv run textual run --dev phyrax.app:PhyraxApp
