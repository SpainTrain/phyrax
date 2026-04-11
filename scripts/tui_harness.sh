#!/usr/bin/env bash
# tui_harness.sh — tmux-based interactive TUI test harness for Phyrax.
#
# Usage:
#   ./scripts/tui_harness.sh start          Start detached tmux session with fixture mailbox
#   ./scripts/tui_harness.sh keys KEY ...   Send one or more keystrokes to the session
#   ./scripts/tui_harness.sh read           Capture the pane and print to stdout
#   ./scripts/tui_harness.sh stop           Kill the session and clean up temp dir
#
# The harness ALWAYS uses a synthetic fixture mailbox — it never touches the
# real notmuch database or real email. A minimal config.json is written to skip
# the FTUX wizard so tests land directly on InboxScreen.
#
# Key names follow tmux conventions: Enter, Escape, Space, Up, Down, Left, Right,
# BSpace, Tab, etc.  Single characters are sent literally: j, k, a, r, q, etc.

set -euo pipefail

SESSION="phyrax_test"
STATE_FILE="/tmp/phyrax_harness_state"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_require_tmux() {
    if ! command -v tmux &>/dev/null; then
        echo "ERROR: tmux is not installed. Install it with: sudo apt install tmux" >&2
        exit 1
    fi
}

_session_exists() {
    tmux has-session -t "$SESSION" 2>/dev/null
}

_setup_fixture() {
    # Build a synthetic fixture mailbox under a fresh temp dir.
    # Writes a minimal config.json so FTUX is skipped.
    # Prints shell export lines to stdout.
    REPO_ROOT="$REPO_ROOT" "$REPO_ROOT/scripts/_fixture_env.sh"
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_start() {
    _require_tmux

    if _session_exists; then
        echo "Session '$SESSION' already running. Use 'stop' first." >&2
        exit 1
    fi

    echo "Setting up fixture mailbox..." >&2
    eval "$( REPO_ROOT="$REPO_ROOT" _setup_fixture )"

    # Persist state for stop/cleanup
    cat > "$STATE_FILE" <<EOF
HARNESS_TMP=$HARNESS_TMP
EOF

    echo "Starting tmux session '$SESSION'..." >&2
    tmux new-session -d -s "$SESSION" \
        -x 200 -y 50 \
        "cd '$REPO_ROOT' && \
         NOTMUCH_CONFIG='$NOTMUCH_CONFIG' \
         XDG_CONFIG_HOME='$XDG_CONFIG_HOME' \
         XDG_CACHE_HOME='$XDG_CACHE_HOME' \
         XDG_STATE_HOME='$XDG_STATE_HOME' \
         PHYRAX_LOG_LEVEL=DEBUG \
         uv run phr; bash"

    # Wait for the TUI to render
    sleep 2
    echo "Session '$SESSION' started. Fixture: $HARNESS_TMP" >&2
}

cmd_keys() {
    _require_tmux

    if ! _session_exists; then
        echo "No session '$SESSION'. Run 'start' first." >&2
        exit 1
    fi

    shift  # remove 'keys' subcommand
    for key in "$@"; do
        tmux send-keys -t "$SESSION" "$key"
        sleep 0.15
    done
}

cmd_read() {
    _require_tmux

    if ! _session_exists; then
        echo "No session '$SESSION'. Run 'start' first." >&2
        exit 1
    fi

    # Capture pane, strip trailing whitespace on each line, remove trailing blank lines
    tmux capture-pane -t "$SESSION" -p \
        | sed 's/[[:space:]]*$//' \
        | awk 'NF{found=NR} END{for(i=1;i<=found;i++) print lines[i]} {lines[NR]=$0}'
}

cmd_stop() {
    _require_tmux

    if _session_exists; then
        tmux kill-session -t "$SESSION"
        echo "Session '$SESSION' stopped." >&2
    else
        echo "No session '$SESSION' running." >&2
    fi

    # Clean up fixture temp dir
    if [[ -f "$STATE_FILE" ]]; then
        source "$STATE_FILE"
        if [[ -n "${HARNESS_TMP:-}" && -d "$HARNESS_TMP" ]]; then
            rm -rf "$HARNESS_TMP"
            echo "Cleaned up fixture: $HARNESS_TMP" >&2
        fi
        rm -f "$STATE_FILE"
    fi
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

case "${1:-}" in
    start)  cmd_start "$@" ;;
    keys)   cmd_keys "$@" ;;
    read)   cmd_read ;;
    stop)   cmd_stop ;;
    *)
        echo "Usage: $0 {start|keys KEY...|read|stop}" >&2
        exit 1
        ;;
esac
