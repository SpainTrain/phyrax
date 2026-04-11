"""Synthetic Maildir fixture generator for Phyrax tests.

Builds a Maildir containing exactly 10 threads / 29 messages, runs
``notmuch new`` to index them, and applies bundle tags.  Designed for
use from the ``tmp_maildir`` pytest fixture in ``tests/conftest.py``.

Thread layout
-------------
1.  3 msgs  — alerts@example.com        "Alert: Server Down"         tags: inbox unread alerts
2.  2 msgs  — newsletter@substack.com   "Weekly Digest"              tags: inbox unread newsletters
3.  4 msgs  — boss@company.com          "Q2 Planning"                tags: inbox unread
4.  1 msg   — docs@example.com          "Docs Attachment"            tags: inbox unread (multipart)
5.  3 msgs  — friend@example.com        reply chain                  tags: inbox unread
6.  1 msg   — github@github.com         "PR review: fix auth"        tags: inbox unread
7.  1 msg   — noreply@notion.so         "Your weekly Notion digest"  tags: inbox unread newsletters
8.  1 msg   — recruiter@talent.io       "Exciting opportunity"       tags: inbox unread
9.  2 msgs  — alice@startup.io          "Coffee chat this week?"     tags: inbox unread
10. 1 msg   — support@stripe.com        "Your invoice is ready"      tags: inbox unread alerts

Every message carries: X-GM-THRID, Message-ID, From, To, Date, Subject.
"""

from __future__ import annotations

import base64
import email.utils
import subprocess
import textwrap
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path

# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MaildirFixture:
    """Return value of :func:`build_maildir`."""

    maildir: Path
    notmuch_config: Path
    thread_ids: dict[str, str] = field(default_factory=dict)
    """Mapping of human label → notmuch thread-ID (populated after indexing)."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Stable base timestamp (2025-01-01 12:00:00 UTC)
_BASE_TS = 1_735_732_800


def _ts(offset_minutes: int = 0) -> int:
    """Return a deterministic Unix timestamp offset from the base."""
    return _BASE_TS + offset_minutes * 60


def _formatdate(offset_minutes: int = 0) -> str:
    """RFC 2822 formatted date string."""
    return email.utils.formatdate(_ts(offset_minutes), usegmt=True)


def _make_message_id(label: str) -> str:
    return f"<{label}@fixture.phyrax.test>"


def _write_message(maildir: Path, msg: EmailMessage, filename: str) -> None:
    """Write *msg* into ``maildir/cur/``."""
    cur = maildir / "cur"
    (cur / filename).write_bytes(msg.as_bytes())


def _build_plain_message(
    *,
    from_: str,
    to: str,
    subject: str,
    body: str,
    date_offset: int,
    message_id: str,
    in_reply_to: str | None,
    references: str | None,
    gm_thrid: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = _formatdate(date_offset)
    msg["Message-ID"] = message_id
    msg["X-GM-THRID"] = gm_thrid
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)
    return msg


def _build_attachment_message(
    *,
    from_: str,
    to: str,
    subject: str,
    body: str,
    date_offset: int,
    message_id: str,
    gm_thrid: str,
    attachment_name: str,
    attachment_bytes: bytes,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = _formatdate(date_offset)
    msg["Message-ID"] = message_id
    msg["X-GM-THRID"] = gm_thrid
    msg.set_content(body)
    msg.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="pdf",
        filename=attachment_name,
    )
    return msg


def _notmuch_config_text(maildir: Path) -> str:
    return textwrap.dedent(f"""\
        [database]
        path={maildir}

        [user]
        name=Test User
        primary_email=test@example.com

        [new]
        tags=inbox;unread;
        ignore=

        [search]
        exclude_tags=deleted;spam;

        [maildir]
        synchronize_flags=false
    """)


def _run(args: list[str], *, config: Path) -> None:
    """Run a notmuch command with the fixture config."""
    env_config = str(config)
    subprocess.run(
        args,
        check=True,
        capture_output=True,
        env={"NOTMUCH_CONFIG": env_config, "HOME": str(config.parent)},
    )


def _get_thread_id(notmuch_config: Path, message_id: str) -> str:
    """Retrieve the notmuch thread ID for *message_id*."""
    result = subprocess.run(
        ["notmuch", "search", "--output=threads", f"id:{message_id.strip('<>')}"],
        check=True,
        capture_output=True,
        text=True,
        env={
            "NOTMUCH_CONFIG": str(notmuch_config),
            "HOME": str(notmuch_config.parent),
        },
    )
    return result.stdout.strip()


def _apply_tag(notmuch_config: Path, thread_id: str, tag_expr: str) -> None:
    """Apply a tag expression (e.g. ``+alerts``) to *thread_id*.

    *thread_id* may be a bare hex ID or the full ``thread:XXXX`` string
    returned by ``notmuch search --output=threads``.
    """
    bare_id = thread_id.removeprefix("thread:")
    _run(
        ["notmuch", "tag", tag_expr, f"thread:{bare_id}"],
        config=notmuch_config,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_maildir(root: Path) -> MaildirFixture:
    """Generate the synthetic Maildir fixture under *root*.

    Creates:
    - ``root/``  (Maildir: cur/, new/, tmp/)
    - ``root/../notmuch-config``  (minimal notmuch config)

    Runs ``notmuch new`` and applies per-thread tags.

    Returns a :class:`MaildirFixture` with paths and discovered thread IDs.
    """
    # ------------------------------------------------------------------ dirs
    maildir = root / "mail"
    for sub in ("cur", "new", "tmp"):
        (maildir / sub).mkdir(parents=True, exist_ok=True)

    notmuch_config = root / "notmuch-config"
    notmuch_config.write_text(_notmuch_config_text(maildir))

    # ------------------------------------------------------------------ thread 1: alerts (3 msgs)
    t1_thrid = "111000000000001"
    t1_ids: list[str] = [
        _make_message_id("alert-1"),
        _make_message_id("alert-2"),
        _make_message_id("alert-3"),
    ]
    for idx, mid in enumerate(t1_ids):
        prev_id = t1_ids[idx - 1] if idx > 0 else None
        refs = " ".join(t1_ids[:idx]) if idx > 0 else None
        msg = _build_plain_message(
            from_="alerts@example.com",
            to="test@example.com",
            subject="Alert: Server Down",
            body=f"Alert message {idx + 1}: server is down.",
            date_offset=idx * 5,
            message_id=mid,
            in_reply_to=prev_id,
            references=refs,
            gm_thrid=t1_thrid,
        )
        _write_message(maildir, msg, f"alert-{idx + 1}.eml")

    # -------------------------------------------------------- thread 2: newsletter (2 msgs)
    t2_thrid = "222000000000002"
    t2_ids: list[str] = [
        _make_message_id("newsletter-1"),
        _make_message_id("newsletter-2"),
    ]
    for idx, mid in enumerate(t2_ids):
        prev_id = t2_ids[idx - 1] if idx > 0 else None
        refs = t2_ids[0] if idx > 0 else None
        msg = _build_plain_message(
            from_="newsletter@substack.com",
            to="test@example.com",
            subject="Weekly Digest",
            body=f"Weekly digest edition {idx + 1}.",
            date_offset=10 + idx * 5,
            message_id=mid,
            in_reply_to=prev_id,
            references=refs,
            gm_thrid=t2_thrid,
        )
        _write_message(maildir, msg, f"newsletter-{idx + 1}.eml")

    # ------------------------------------------------------------------ thread 3: boss (4 msgs)
    t3_thrid = "333000000000003"
    t3_ids: list[str] = [
        _make_message_id("q2-1"),
        _make_message_id("q2-2"),
        _make_message_id("q2-3"),
        _make_message_id("q2-4"),
    ]
    for idx, mid in enumerate(t3_ids):
        prev_id = t3_ids[idx - 1] if idx > 0 else None
        refs = " ".join(t3_ids[:idx]) if idx > 0 else None
        msg = _build_plain_message(
            from_="boss@company.com",
            to="test@example.com",
            subject="Q2 Planning",
            body=f"Q2 planning update {idx + 1}.",
            date_offset=20 + idx * 10,
            message_id=mid,
            in_reply_to=prev_id,
            references=refs,
            gm_thrid=t3_thrid,
        )
        _write_message(maildir, msg, f"q2-{idx + 1}.eml")

    # -------------------------------------------------------- thread 4: attachment (1 msg)
    t4_thrid = "444000000000004"
    t4_id = _make_message_id("docs-1")
    # Minimal fake PDF bytes (not a real PDF — just fake bytes for testing)
    fake_pdf = base64.b64decode(
        "JVBERi0xLjAKMSAwIG9iajw8L1R5cGUvQ2F0YWxvZy9QYWdlcyAyIDAgUj4+ZW5kb2JqCjIg"
        "MCBvYmo8PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PmVuZG9iagozIDAgb2Jq"
        "PDwvVHlwZS9QYWdlL01lZGlhQm94WzAgMCAzIDNdPj5lbmRvYmoKeHJlZgowIDQKMDAwMDAw"
        "MDAwMCA2NTUzNSBmIAowMDAwMDAwMDA5IDAwMDAwIG4gCjAwMDAwMDAwNTggMDAwMDAgbiAK"
        "MDAwMDAwMDExNSAwMDAwMCBuIAp0cmFpbGVyPDwvU2l6ZSA0L1Jvb3QgMSAwIFI+PgpzdGFy"
        "dHhyZWYKMTkwCiUlRU9G"
    )
    msg4 = _build_attachment_message(
        from_="docs@example.com",
        to="test@example.com",
        subject="Docs Attachment",
        body="Please find the attached PDF document.",
        date_offset=60,
        message_id=t4_id,
        gm_thrid=t4_thrid,
        attachment_name="document.pdf",
        attachment_bytes=fake_pdf,
    )
    _write_message(maildir, msg4, "docs-1.eml")

    # -------------------------------------------------------- thread 5: reply chain (3 msgs)
    t5_thrid = "555000000000005"
    t5_ids: list[str] = [
        _make_message_id("friend-1"),
        _make_message_id("friend-2"),
        _make_message_id("friend-3"),
    ]
    t5_bodies = [
        "Hey! How are you doing?",
        (
            "On Mon, Jan 01 2025 friend@example.com wrote:\n"
            "> Hey! How are you doing?\n\n"
            "I'm great, thanks!"
        ),
        (
            "On Mon, Jan 01 2025 friend@example.com wrote:\n"
            "> On Mon, Jan 01 2025 friend@example.com wrote:\n"
            ">> Hey! How are you doing?\n"
            "> I'm great, thanks!\n\n"
            "Glad to hear it! Let's catch up soon."
        ),
    ]
    for idx, (mid, body) in enumerate(zip(t5_ids, t5_bodies, strict=True)):
        prev_id = t5_ids[idx - 1] if idx > 0 else None
        refs = " ".join(t5_ids[:idx]) if idx > 0 else None
        msg = _build_plain_message(
            from_="friend@example.com",
            to="test@example.com",
            subject="Re: Catching up" if idx > 0 else "Catching up",
            body=body,
            date_offset=70 + idx * 15,
            message_id=mid,
            in_reply_to=prev_id,
            references=refs,
            gm_thrid=t5_thrid,
        )
        _write_message(maildir, msg, f"friend-{idx + 1}.eml")

    # -------------------------------------------------------- thread 6: github PR (1 msg)
    t6_thrid = "666000000000006"
    t6_id = _make_message_id("github-pr-1")
    msg6 = _build_plain_message(
        from_="github@github.com",
        to="test@example.com",
        subject="PR review requested: fix auth middleware",
        body=(
            "SpainTrain requested your review on pull request #42: fix auth middleware.\n\n"
            "Touches: src/auth/middleware.py, tests/test_auth.py\n\n"
            "View the pull request: https://github.com/example/repo/pull/42"
        ),
        date_offset=100,
        message_id=t6_id,
        in_reply_to=None,
        references=None,
        gm_thrid=t6_thrid,
    )
    _write_message(maildir, msg6, "github-pr-1.eml")

    # -------------------------------------------------------- thread 7: notion digest (1 msg)
    t7_thrid = "777000000000007"
    t7_id = _make_message_id("notion-digest-1")
    msg7 = _build_plain_message(
        from_="noreply@notion.so",
        to="test@example.com",
        subject="Your weekly Notion digest",
        body=(
            "Here's what happened in your Notion workspace this week:\n\n"
            "- 5 pages updated\n"
            "- 2 new comments\n"
            "- 1 database record added\n\n"
            "View your workspace: https://notion.so/workspace"
        ),
        date_offset=110,
        message_id=t7_id,
        in_reply_to=None,
        references=None,
        gm_thrid=t7_thrid,
    )
    _write_message(maildir, msg7, "notion-digest-1.eml")

    # -------------------------------------------------------- thread 8: recruiter (1 msg)
    t8_thrid = "888000000000008"
    t8_id = _make_message_id("recruiter-1")
    msg8 = _build_plain_message(
        from_="recruiter@talent.io",
        to="test@example.com",
        subject="Exciting opportunity at Acme Corp",
        body=(
            "Hi there,\n\n"
            "I came across your profile and think you'd be a great fit for a senior "
            "engineering role at Acme Corp. The team is working on some really exciting "
            "infrastructure challenges.\n\n"
            "Would you be open to a 15-minute chat this week?\n\n"
            "Best,\nJordan\nTalent.io"
        ),
        date_offset=120,
        message_id=t8_id,
        in_reply_to=None,
        references=None,
        gm_thrid=t8_thrid,
    )
    _write_message(maildir, msg8, "recruiter-1.eml")

    # -------------------------------------------------------- thread 9: alice coffee chat (2 msgs)
    t9_thrid = "999000000000009"
    t9_ids: list[str] = [
        _make_message_id("alice-1"),
        _make_message_id("alice-2"),
    ]
    t9_bodies = [
        "Hey! Would you be up for a coffee chat this week? I'm curious about the new project.",
        (
            "On Wed, Jan 01 2025 alice@startup.io wrote:\n"
            "> Would you be up for a coffee chat this week?\n\n"
            "Absolutely! How about Thursday at 3pm?"
        ),
    ]
    for idx, (mid, body) in enumerate(zip(t9_ids, t9_bodies, strict=True)):
        prev_id = t9_ids[idx - 1] if idx > 0 else None
        refs = t9_ids[0] if idx > 0 else None
        msg = _build_plain_message(
            from_="alice@startup.io",
            to="test@example.com",
            subject="Re: Coffee chat this week?" if idx > 0 else "Coffee chat this week?",
            body=body,
            date_offset=130 + idx * 10,
            message_id=mid,
            in_reply_to=prev_id,
            references=refs,
            gm_thrid=t9_thrid,
        )
        _write_message(maildir, msg, f"alice-{idx + 1}.eml")

    # -------------------------------------------------------- thread 10: stripe invoice (1 msg)
    t10_thrid = "aaa000000000010"
    t10_id = _make_message_id("stripe-invoice-1")
    msg10 = _build_plain_message(
        from_="support@stripe.com",
        to="test@example.com",
        subject="Your invoice is ready",
        body=(
            "Your invoice #INV-2025-001 for $49.00 is now available.\n\n"
            "Billing period: January 2025\n"
            "Amount due: $49.00\n\n"
            "View and download your invoice: https://dashboard.stripe.com/invoices"
        ),
        date_offset=150,
        message_id=t10_id,
        in_reply_to=None,
        references=None,
        gm_thrid=t10_thrid,
    )
    _write_message(maildir, msg10, "stripe-invoice-1.eml")

    # ------------------------------------------------------------------ notmuch new
    # Use NOTMUCH_CONFIG env var (already set by _run); --config flag not
    # supported by older notmuch versions.
    _run(["notmuch", "new"], config=notmuch_config)

    # ------------------------------------------------------------------ discover thread IDs
    # Use the first message-ID in each thread to look up the notmuch thread ID.
    anchor_message_ids = {
        "alerts": t1_ids[0],
        "newsletters": t2_ids[0],
        "boss": t3_ids[0],
        "docs": t4_id,
        "friend": t5_ids[0],
        "github": t6_id,
        "notion": t7_id,
        "recruiter": t8_id,
        "alice": t9_ids[0],
        "stripe": t10_id,
    }

    thread_ids: dict[str, str] = {}
    for label, mid in anchor_message_ids.items():
        tid = _get_thread_id(notmuch_config, mid)
        thread_ids[label] = tid

    # ------------------------------------------------------------------ apply bundle tags
    # notmuch new already applies +inbox +unread (from [new] tags in config).
    # Add the extra bundle-specific tags.
    if thread_ids.get("alerts"):
        _apply_tag(notmuch_config, thread_ids["alerts"], "+alerts")
    if thread_ids.get("stripe"):
        _apply_tag(notmuch_config, thread_ids["stripe"], "+alerts")
    if thread_ids.get("newsletters"):
        _apply_tag(notmuch_config, thread_ids["newsletters"], "+newsletters")
    if thread_ids.get("notion"):
        _apply_tag(notmuch_config, thread_ids["notion"], "+newsletters")

    return MaildirFixture(
        maildir=maildir,
        notmuch_config=notmuch_config,
        thread_ids=thread_ids,
    )
