"""Phyrax CLI — entrypoint for both TUI and headless subcommands."""

from __future__ import annotations

import typer

from phyrax.app import run_app
from phyrax.config import PhyraxConfig
from phyrax.database import Database

app = typer.Typer(
    name="phr",
    help="Phyrax: a keyboard-first, AI-assisted terminal email client.",
    no_args_is_help=False,
)


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
