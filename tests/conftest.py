"""Shared pytest fixtures for Phyrax tests.

Three core fixtures:
- tmp_config_dir: XDG-like temp dir tree with a minimal valid config.json
- tmp_maildir: synthetic Maildir with 5 threads / 20 messages, notmuch-indexed
- mock_agent_command: path to a shell script that echoes its stdin back
"""

from __future__ import annotations

import json
import stat
import textwrap
from pathlib import Path

import pytest

from tests.fixtures.maildir_builder import MaildirFixture, build_maildir


@pytest.fixture()
def tmp_config_dir(tmp_path: Path) -> Path:
    """Return a temp XDG config dir with a minimal valid config.json.

    Directory layout mirrors the real XDG paths used by Phyrax:
        <tmp>/config/phyrax/config.json
        <tmp>/cache/phyrax/
        <tmp>/state/phyrax/
    """
    config_dir = tmp_path / "config" / "phyrax"
    config_dir.mkdir(parents=True)
    (tmp_path / "cache" / "phyrax").mkdir(parents=True)
    (tmp_path / "state" / "phyrax").mkdir(parents=True)

    minimal_config = {
        "identity": {
            "primary": "test@example.com",
            "aliases": [],
        },
        "ai": {
            "agent_command": "echo",
        },
        "bundles": [],
        "compose": {
            "include_quote": True,
        },
    }
    (config_dir / "config.json").write_text(json.dumps(minimal_config, indent=2))
    return tmp_path


@pytest.fixture()
def tmp_maildir(tmp_path: Path) -> MaildirFixture:
    """Return a synthetic Maildir fixture with 5 threads / 20 messages.

    Builds the Maildir under *tmp_path*, runs ``notmuch new`` to index
    it, and applies bundle tags (+alerts, +newsletters).  Returns a
    :class:`~tests.fixtures.maildir_builder.MaildirFixture` namedtuple
    containing:

    - ``maildir``       — Path to the Maildir root (``cur/``, ``new/``, ``tmp/``)
    - ``notmuch_config``— Path to the minimal notmuch config file
    - ``thread_ids``    — dict mapping label → notmuch thread ID
    """
    return build_maildir(tmp_path)


@pytest.fixture()
def mock_agent_command(tmp_path: Path) -> str:
    """Return the path to a shell script that echoes its stdin to stdout.

    Tests that exercise agent.run_agent() can point config.ai.agent_command
    here to get a deterministic, fast response without calling a real LLM.
    """
    script = tmp_path / "mock_agent.sh"
    script.write_text(
        textwrap.dedent("""\
            #!/usr/bin/env sh
            # Mock AI agent: echo stdin back as stdout.
            cat
        """)
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(script)
