"""Phyrax CLI — entrypoint for both TUI and headless subcommands."""

from __future__ import annotations

import typer

from phyrax.app import run_app

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
