"""Draft composition pipeline.

Lifecycle:
1. pick_alias() selects the outgoing From address.
2. generate_draft() calls the AI agent (captured) and returns a Draft.
3. save_draft() writes an RFC 5322 file: headers + blank line + Markdown body.
4. open_editor() suspends the TUI, opens $EDITOR, re-parses on exit.
5. recover_unsent_drafts() scans DRAFTS_DIR for orphaned .txt files.
6. cleanup_draft() deletes the cache file after a successful send.

Draft file format (RFC 5322):
    From: mike@spainhower.me
    To: alice@example.com
    Subject: Re: project update
    In-Reply-To: <abc@mail.gmail.com>
    References: <abc@mail.gmail.com>

    Markdown body here…

    On Mon Apr 6 2026, Alice wrote:
    > quoted original (when compose.include_quote is True)
"""

from __future__ import annotations

import email.message
import email.parser
import logging
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from phyrax.agent import RunMode, compile_prompt, run_agent
from phyrax.config import DRAFTS_DIR, PhyraxConfig
from phyrax.exceptions import ComposeError
from phyrax.models import Draft, MessageDetail

log = logging.getLogger("phyrax")


def pick_alias(message: MessageDetail, config: PhyraxConfig) -> str:
    """Choose the outgoing From address for a reply.

    Scans the original message's To, Cc, and Delivered-To headers.
    Returns the first alias from config.identity.aliases that matches,
    or config.identity.primary if none match.
    """
    candidate_addrs: list[str] = []
    candidate_addrs.extend(message.to)
    candidate_addrs.extend(message.cc)
    delivered_to = message.headers.get("Delivered-To", "")
    if delivered_to:
        candidate_addrs.append(delivered_to)

    candidate_lower = {a.lower() for a in candidate_addrs}
    for alias in config.identity.aliases:
        if alias.lower() in candidate_lower:
            return alias
    return config.identity.primary


def _build_quote(message: MessageDetail) -> str:
    """Build a quoted-reply block from the original message."""
    dt = datetime.fromtimestamp(message.date, tz=UTC)
    date_str = dt.strftime("%a, %b %d %Y at %H:%M")
    attribution = f"On {date_str}, {message.from_} wrote:"
    quoted_lines = "\n".join(f"> {line}" for line in (message.body_plain or "").splitlines())
    return f"\n\n{attribution}\n{quoted_lines}"


def generate_draft(
    message: MessageDetail,
    instructions: str,
    config: PhyraxConfig,
    *,
    require_full_context: bool = False,
) -> Draft:
    """Use the AI agent (captured) to produce a draft body and return a Draft."""
    prompt_path = compile_prompt(
        instructions,
        message,
        require_full_context=require_full_context,
    )
    try:
        result = run_agent(
            config.ai.agent_command,
            prompt_path,
            mode=RunMode.CAPTURED,
            fallback_command=config.ai.fallback_command,
        )
        body = result.stdout.strip()
    finally:
        prompt_path.unlink(missing_ok=True)

    draft_uuid = str(uuid.uuid4())
    alias = pick_alias(message, config)

    return Draft(
        uuid=draft_uuid,
        thread_id=message.thread_id,
        in_reply_to=message.message_id,
        to=[message.from_],
        cc=message.cc,
        subject=f"Re: {message.subject}",
        from_=alias,
        body_markdown=body,
        cache_path=DRAFTS_DIR / f"{draft_uuid}.txt",
    )


def save_draft(draft: Draft, config: PhyraxConfig | None = None) -> None:
    """Write the draft to ~/.cache/phyrax/drafts/{uuid}.txt in RFC 5322 format."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    msg = email.message.Message()
    msg["From"] = draft.from_
    msg["To"] = ", ".join(draft.to)
    if draft.cc:
        msg["Cc"] = ", ".join(draft.cc)
    msg["Subject"] = draft.subject
    msg["In-Reply-To"] = draft.in_reply_to
    msg["References"] = draft.in_reply_to
    msg["X-Phyrax-Thread-Id"] = draft.thread_id
    msg["X-Phyrax-Uuid"] = draft.uuid

    # email.message.Message.__str__ includes a trailing newline, so appending
    # the body without an extra separator is correct — the blank line between
    # headers and body is already present in the str() output.
    header_str = str(msg)

    body = draft.body_markdown
    draft.cache_path.write_text(header_str + body, encoding="utf-8")
    log.debug("Saved draft %s to %s", draft.uuid, draft.cache_path)


def _parse_draft(path: Path) -> Draft:
    """Parse an RFC 5322 draft file back into a Draft dataclass.

    Raises:
        ComposeError: If the file is missing required fields or has no blank line.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ComposeError(f"Cannot read draft file {path}: {exc}") from exc

    # Find the blank line separating headers from body.
    blank_line_idx = raw.find("\n\n")
    if blank_line_idx == -1:
        raise ComposeError(f"Malformed draft (no header/body separator): {path}")
    body = raw[blank_line_idx + 2 :]

    parser = email.parser.Parser()
    # headersonly=True prevents any MIME parsing of the body section.
    msg = parser.parsestr(raw, headersonly=True)

    try:
        return Draft(
            uuid=msg["X-Phyrax-Uuid"] or path.stem,
            thread_id=msg["X-Phyrax-Thread-Id"] or "",
            in_reply_to=msg["In-Reply-To"] or "",
            to=[a.strip() for a in (msg["To"] or "").split(",") if a.strip()],
            cc=[a.strip() for a in (msg["Cc"] or "").split(",") if a.strip()],
            subject=msg["Subject"] or "",
            from_=msg["From"] or "",
            body_markdown=body,
            cache_path=path,
        )
    except Exception as exc:
        raise ComposeError(f"Malformed draft {path}: {exc}") from exc


def open_editor(draft: Draft) -> Draft:
    """Open $EDITOR on the draft file; re-parse headers/body on return.

    TUI suspension (App.suspend()) must happen at the call site before
    invoking this function.

    Returns:
        A new Draft reflecting any header or body edits the user made.

    Raises:
        ComposeError: If the file is malformed after editing.
    """
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(draft.cache_path)], check=False)
    return _parse_draft(draft.cache_path)


def recover_unsent_drafts() -> list[Draft]:
    """Scan DRAFTS_DIR for orphaned .txt files and return parsed Drafts.

    Malformed files are skipped with a warning rather than raising.
    """
    if not DRAFTS_DIR.exists():
        return []
    drafts: list[Draft] = []
    for path in sorted(DRAFTS_DIR.glob("*.txt")):
        try:
            drafts.append(_parse_draft(path))
        except ComposeError:
            log.warning("Skipping malformed draft file: %s", path)
    return drafts


def cleanup_draft(draft: Draft) -> None:
    """Delete the draft's cache file (call after a successful send)."""
    draft.cache_path.unlink(missing_ok=True)
    log.debug("Deleted draft %s", draft.cache_path)
