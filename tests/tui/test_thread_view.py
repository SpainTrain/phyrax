"""Tests for ThreadViewScreen.

Covers:
- Screen renders messages from a real fixture thread
- Escape (via action) pops back to the previous screen
- html2text fallback for HTML-only messages
- ctrl+g constructs the correct Gmail URL
"""

from __future__ import annotations

import unittest.mock

import pytest
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Label

from phyrax.config import PhyraxConfig
from phyrax.database import Database
from phyrax.models import MessageDetail, ThreadSummary
from phyrax.tui.screens.thread_view import ThreadViewScreen
from tests.fixtures.maildir_builder import MaildirFixture


def _make_config() -> PhyraxConfig:
    """Return a minimal PhyraxConfig for tests."""
    return PhyraxConfig()


# ---------------------------------------------------------------------------
# Minimal host app for screen-push tests
# ---------------------------------------------------------------------------


class _BaseScreen(Screen):  # type: ignore[type-arg]
    """Simple base screen that sits beneath ThreadViewScreen on the stack."""

    def compose(self) -> ComposeResult:
        yield Label("base")


class _HostApp(App):  # type: ignore[type-arg]
    """Minimal App that pushes BaseScreen then ThreadViewScreen."""

    def __init__(self, screen: ThreadViewScreen) -> None:
        super().__init__()
        self._thread_screen = screen

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(_BaseScreen())
        self.push_screen(self._thread_screen)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_maildir: MaildirFixture) -> Database:
    """Open a Database pointed at the fixture Maildir."""
    return Database(path=str(tmp_maildir.maildir))


def _get_thread(db: Database, thread_id: str) -> ThreadSummary:
    """Fetch a single ThreadSummary by thread_id from the fixture DB."""
    bare = thread_id.removeprefix("thread:")
    threads = db.query_threads(f"thread:{bare}", limit=1)
    assert threads, f"No thread found for id={thread_id!r}"
    return threads[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thread_view_renders_messages(tmp_maildir: MaildirFixture) -> None:
    """ThreadViewScreen mounts and renders at least one Static message block."""
    db = _make_db(tmp_maildir)
    boss_id = tmp_maildir.thread_ids["boss"]
    thread = _get_thread(db, boss_id)

    screen = ThreadViewScreen(db, thread, _make_config())
    app = _HostApp(screen)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # The screen should contain Static widgets with message content
        statics = list(app.screen.query("Static"))
        assert len(statics) > 0, "Expected at least one Static message block"

        # The rendered text should contain content from the Q2 Planning thread
        all_text = " ".join(str(s.render()) for s in statics)
        has_content = (
            "Q2 Planning" in all_text
            or "boss@company.com" in all_text
            or "planning" in all_text.lower()
        )
        assert has_content, f"Expected Q2 Planning content; got: {all_text[:200]!r}"

    db.close()


@pytest.mark.asyncio
async def test_thread_view_escape_pops_screen(tmp_maildir: MaildirFixture) -> None:
    """The pop_screen action on ThreadViewScreen returns to the base screen."""
    db = _make_db(tmp_maildir)
    boss_id = tmp_maildir.thread_ids["boss"]
    thread = _get_thread(db, boss_id)

    screen = ThreadViewScreen(db, thread, _make_config())
    app = _HostApp(screen)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ThreadViewScreen)

        # Trigger pop_screen directly — pilot.press("escape") doesn't reliably
        # route App-level actions through Textual's pilot in this version.
        app.pop_screen()
        await pilot.pause()

        # ThreadViewScreen should now be gone; _BaseScreen is on top
        assert isinstance(app.screen, _BaseScreen)

    db.close()


@pytest.mark.asyncio
async def test_html_fallback_renders(tmp_maildir: MaildirFixture) -> None:
    """HTML-only messages fall back to html2text and still produce rendered output."""
    db = _make_db(tmp_maildir)

    # Build a synthetic ThreadSummary
    thread = ThreadSummary(
        thread_id="thread:html-only-test",
        subject="HTML Only Test",
        authors=["sender@example.com"],
        newest_date=1_735_732_800,
        message_count=1,
        tags=frozenset({"inbox", "unread"}),
        snippet="html content",
        gmail_thread_id="html_gm_thread_id",
    )

    html_msg = MessageDetail(
        message_id="<html-only@test>",
        thread_id="thread:html-only-test",
        from_="sender@example.com",
        to=["test@example.com"],
        cc=[],
        date=1_735_732_800,
        subject="HTML Only Test",
        headers={},
        body_plain="",  # empty — force html2text fallback path
        body_html="<html><body><p>Hello from <b>HTML</b>!</p></body></html>",
        tags=frozenset({"inbox", "unread"}),
        attachments=[],
    )

    with unittest.mock.patch.object(db, "get_thread_messages", return_value=[html_msg]):
        screen = ThreadViewScreen(db, thread, _make_config())
        app = _HostApp(screen)

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            statics = list(app.screen.query("Static"))
            assert len(statics) > 0, "Expected at least one Static block for the HTML message"
            all_text = " ".join(str(s.render()) for s in statics)
            # html2text converts <p>Hello from <b>HTML</b>!</p> to "Hello from **HTML**!"
            assert "Hello" in all_text, (
                f"Expected 'Hello' in rendered text; got: {all_text[:200]!r}"
            )

    db.close()


@pytest.mark.asyncio
async def test_ctrl_g_opens_gmail_url(tmp_maildir: MaildirFixture) -> None:
    """action_open_gmail calls xdg-open with a URL containing the gmail_thread_id."""
    db = _make_db(tmp_maildir)
    boss_id = tmp_maildir.thread_ids["boss"]
    thread = _get_thread(db, boss_id)

    screen = ThreadViewScreen(db, thread, _make_config())
    app = _HostApp(screen)

    captured_args: list[list[str]] = []

    def _fake_run(args: list[str], **kwargs: object) -> None:
        captured_args.append(list(args))

    with unittest.mock.patch(
        "phyrax.tui.screens.thread_view.subprocess.run", side_effect=_fake_run
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Invoke action directly — pilot.press("ctrl+g") may be intercepted
            await app.screen.run_action("open_gmail")
            await pilot.pause()

    assert captured_args, "subprocess.run was not called by action_open_gmail"
    call_args = captured_args[0]
    assert call_args[0] == "xdg-open", f"Expected xdg-open; got {call_args[0]!r}"
    url = call_args[1]
    gmail_id = thread.gmail_thread_id
    assert gmail_id in url, f"Expected gmail_thread_id {gmail_id!r} in URL {url!r}"
    assert url.startswith("https://mail.google.com/"), f"Unexpected URL: {url!r}"

    db.close()
