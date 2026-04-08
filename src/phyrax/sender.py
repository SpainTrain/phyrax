"""Email dispatch — Markdown → HTML → multipart MIME → gmi send -t.

Phyrax handles MIME construction; lieer (gmi) handles the Gmail API transport.
pandoc invocation: ``pandoc -f gfm -t html5 --no-standalone`` (stdin → stdout).
The returned HTML fragment is wrapped in a minimal inline-styled envelope.
"""

from __future__ import annotations

from phyrax.models import Draft


def render_html(markdown: str) -> str:
    """Convert Markdown to an HTML string via pandoc.

    Invokes: pandoc -f gfm -t html5 --no-standalone
    Wraps the output fragment in <html><body style="font-family:sans-serif;">…</body></html>.

    Raises:
        SendError: If pandoc exits non-zero.
    """
    raise NotImplementedError


def send_reply(draft: Draft) -> None:
    """Compile the draft to MIME and pipe it to ``gmi send -t``.

    Steps:
    1. Render body_markdown to HTML via render_html().
    2. Build EmailMessage (multipart/alternative: text/plain + text/html).
    3. Set From, To, Cc, Subject, In-Reply-To, References, Message-ID.
    4. subprocess.run(["gmi", "send", "-t"], input=message.as_bytes(), check=True).
    5. On success, call cleanup_draft(draft).

    Raises:
        SendError: If gmi exits non-zero.
    """
    raise NotImplementedError


def preview_in_browser(html_body: str) -> None:
    """Write HTML to a NamedTemporaryFile and open it in the default browser."""
    raise NotImplementedError
