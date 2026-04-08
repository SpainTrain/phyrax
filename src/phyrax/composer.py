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

from phyrax.models import Draft, MessageDetail


def pick_alias(message: MessageDetail, config: object) -> str:
    """Choose the outgoing From address for a reply.

    Scans the original message's To, Cc, and Delivered-To headers.
    Returns the first alias from config.identity.aliases that matches,
    or config.identity.primary if none match.
    """
    raise NotImplementedError


def generate_draft(
    message: MessageDetail,
    instructions: str,
    config: object,
    *,
    require_full_context: bool = False,
) -> Draft:
    """Use the AI agent (captured) to produce a draft body and return a Draft."""
    raise NotImplementedError


def save_draft(draft: Draft) -> None:
    """Write the draft to ~/.cache/phyrax/drafts/{uuid}.txt in RFC 5322 format."""
    raise NotImplementedError


def open_editor(draft: Draft) -> Draft:
    """Suspend the TUI, open $EDITOR on the draft file, re-parse headers on exit.

    Returns:
        A new Draft with any header edits the user made applied.

    Raises:
        ComposeError: If the file is malformed after editing.
    """
    raise NotImplementedError


def recover_unsent_drafts() -> list[Draft]:
    """Scan DRAFTS_DIR for orphaned .txt files and return parsed Drafts."""
    raise NotImplementedError


def cleanup_draft(draft: Draft) -> None:
    """Delete the draft's cache file (call after successful send)."""
    raise NotImplementedError
