"""Phyrax CLI — entrypoint for both TUI and headless subcommands."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Generator
from typing import Annotated

import typer

from phyrax.app import run_app
from phyrax.config import PhyraxConfig
from phyrax.database import Database

app = typer.Typer(
    name="phr",
    help="Phyrax: a keyboard-first, AI-assisted terminal email client.",
    no_args_is_help=False,
)


@contextlib.contextmanager
def _write_lock() -> Generator[None, None, None]:
    """Acquire the PID lockfile or exit 2 if TUI is running."""
    from phyrax.config import LOCKFILE

    if LOCKFILE.exists():
        typer.echo("phr TUI is running; commands disabled", err=True)
        raise typer.Exit(2)
    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    LOCKFILE.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        LOCKFILE.unlink(missing_ok=True)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Launch the Phyrax TUI, or run a headless subcommand."""
    if ctx.invoked_subcommand is None:
        run_app()


@app.command()
def status() -> None:
    """Show inbox and bundle counts as JSON."""
    import json

    try:
        config = PhyraxConfig.load()
        with Database() as db:
            inbox_total = db.count_threads("tag:inbox")
            inbox_unread = db.count_threads("tag:inbox tag:unread")

            bundle_entries: list[dict[str, object]] = []
            for bundle in config.bundles:
                count = db.count_threads(f"tag:{bundle.label}")
                unread = db.count_threads(f"tag:{bundle.label} tag:unread")
                bundle_entries.append({"name": bundle.name, "count": count, "unread": unread})

            if config.bundles:
                not_clause = " OR ".join(f"tag:{b.label}" for b in config.bundles)
                unbundled = db.count_threads(f"tag:inbox AND NOT ({not_clause})")
            else:
                unbundled = inbox_total

        try:
            from phyrax.composer import recover_unsent_drafts

            drafts_pending = len(recover_unsent_drafts())
        except NotImplementedError:
            drafts_pending = 0

        result = {
            "inbox_total": inbox_total,
            "inbox_unread": inbox_unread,
            "bundles": bundle_entries,
            "unbundled": unbundled,
            "drafts_pending": drafts_pending,
        }
        typer.echo(json.dumps(result, indent=2))
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command(name="list")
def list_threads(
    bundle: str | None = typer.Option(None, "--bundle", help="Filter by bundle name"),
    query: str | None = typer.Option(None, "--query", help="Raw notmuch query"),
) -> None:
    """List threads as a JSON array."""
    import json

    try:
        config = PhyraxConfig.load()

        # Build query string
        if query is not None:
            notmuch_query = query
        elif bundle is not None:
            # Resolve bundle name to label
            matched = next((b for b in config.bundles if b.name == bundle), None)
            if matched is None:
                typer.echo(f"Error: bundle {bundle!r} not found in config", err=True)
                raise typer.Exit(1)
            notmuch_query = f"tag:{matched.label}"
        else:
            notmuch_query = "tag:inbox"

        with Database() as db:
            threads = db.query_threads(notmuch_query, limit=500)

        result = [
            {
                "thread_id": t.thread_id,
                "subject": t.subject,
                "authors": t.authors,
                "date_unix": t.newest_date,
                "tags": sorted(t.tags),
                "snippet": t.snippet,
                "gmail_thread_id": t.gmail_thread_id,
            }
            for t in threads
        ]
        typer.echo(json.dumps(result, indent=2))
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command(name="compose")
def compose_draft(
    thread: str | None = typer.Option(None, "--thread", help="Thread ID to reply to"),
    body: str = typer.Option("-", "--body", help="Body text or '-' for stdin"),
    to_addrs: list[str] | None = typer.Option(None, "--to", help="Override To recipients"),  # noqa: B008
    cc_addrs: list[str] | None = typer.Option(None, "--cc", help="Override Cc recipients"),  # noqa: B008
    subject_override: str | None = typer.Option(None, "--subject", help="Override subject"),
    in_reply_to: str | None = typer.Option(None, "--in-reply-to", help="Override In-Reply-To"),
) -> None:
    """Stage a draft reply from the AI agent."""
    import json
    import sys
    import uuid as uuid_mod

    body_text = sys.stdin.read() if body == "-" else body

    with _write_lock():
        try:
            config = PhyraxConfig.load()
            draft_uuid = str(uuid_mod.uuid4())

            if thread:
                with Database() as db:
                    messages = db.get_thread_messages(thread)
                if not messages:
                    typer.echo(f"Error: thread {thread!r} has no messages", err=True)
                    raise typer.Exit(1)
                newest = messages[-1]
                from phyrax.composer import pick_alias

                chosen_to = to_addrs or [newest.from_]
                chosen_cc = cc_addrs or newest.cc
                chosen_subject = subject_override or f"Re: {newest.subject}"
                chosen_in_reply_to = in_reply_to or newest.message_id
                chosen_from = pick_alias(newest, config)
            else:
                chosen_to = to_addrs or []
                chosen_cc = cc_addrs or []
                chosen_subject = subject_override or ""
                chosen_in_reply_to = in_reply_to or ""
                chosen_from = config.identity.primary

            from phyrax.composer import save_draft
            from phyrax.config import DRAFTS_DIR
            from phyrax.models import Draft

            draft = Draft(
                uuid=draft_uuid,
                thread_id=thread or "",
                in_reply_to=chosen_in_reply_to,
                to=chosen_to,
                cc=chosen_cc,
                subject=chosen_subject,
                from_=chosen_from,
                body_markdown=body_text,
                cache_path=DRAFTS_DIR / f"{draft_uuid}.txt",
            )
            save_draft(draft, config)

            typer.echo(
                json.dumps(
                    {
                        "status": "ok",
                        "draft_id": draft_uuid,
                        "path": str(draft.cache_path),
                    },
                    indent=2,
                )
            )
        except typer.Exit:
            raise
        except Exception as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc


@app.command()
def archive(thread_id: Annotated[str, typer.Argument(help="Thread ID to archive")]) -> None:
    """Remove inbox tag from a thread."""
    import json

    with _write_lock():
        with Database() as db:
            db.remove_tags(thread_id, ["inbox"])
            threads = db.query_threads(f"thread:{thread_id}", limit=1)
            tags = sorted(threads[0].tags) if threads else []
        typer.echo(json.dumps({"status": "ok", "thread_id": thread_id, "tags": tags}, indent=2))


@app.command(name="tag")
def tag_thread(
    thread_id: Annotated[str, typer.Argument(help="Thread ID to modify tags on")],
    changes: Annotated[list[str], typer.Argument(help="+add -remove tag changes")],
) -> None:
    """Add or remove tags on a thread. Prefix tags with + or -."""
    import json

    adds = [t[1:] for t in changes if t.startswith("+")]
    removes = [t[1:] for t in changes if t.startswith("-")]
    invalid = [t for t in changes if not t.startswith(("+", "-"))]
    if invalid:
        typer.echo(f"Error: tags must start with + or -: {invalid}", err=True)
        raise typer.Exit(1)
    with _write_lock():
        with Database() as db:
            if adds:
                db.add_tags(thread_id, adds)
            if removes:
                db.remove_tags(thread_id, removes)
            threads = db.query_threads(f"thread:{thread_id}", limit=1)
            tags = sorted(threads[0].tags) if threads else []
        typer.echo(json.dumps({"status": "ok", "thread_id": thread_id, "tags": tags}, indent=2))
