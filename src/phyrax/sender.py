"""Email dispatch — Markdown → HTML → multipart MIME → gmi send -t.

Phyrax handles MIME construction; lieer (gmi) handles the Gmail API transport.
pandoc invocation: ``pandoc -f gfm -t html5 --no-standalone`` (stdin → stdout).
The returned HTML fragment is wrapped in a minimal inline-styled envelope.
"""

from __future__ import annotations

import email.message
import email.utils
import subprocess
import tempfile

from phyrax.composer import _parse_draft, cleanup_draft
from phyrax.exceptions import SendError
from phyrax.models import Draft

_HTML_TEMPLATE = (
    '<html><body style="font-family:sans-serif;line-height:1.5;">{fragment}</body></html>'
)


def render_html(markdown: str) -> str:
    """Convert Markdown to an HTML string via pandoc.

    Invokes: pandoc -f gfm -t html5 --no-standalone
    Wraps the output fragment in <html><body style="font-family:sans-serif;">…</body></html>.

    Raises:
        SendError: If pandoc exits non-zero.
    """
    try:
        result = subprocess.run(
            ["pandoc", "-f", "gfm", "-t", "html5", "--no-standalone"],
            input=markdown.encode("utf-8"),
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SendError(f"pandoc failed: {exc.stderr.decode()}") from exc
    fragment = result.stdout.decode("utf-8")
    return _HTML_TEMPLATE.format(fragment=fragment)


def send_reply(draft: Draft) -> None:
    """Compile the draft to MIME and pipe it to ``gmi send -t``.

    Steps:
    1. Re-parse the draft file so that any user edits are picked up.
    2. Render body_markdown to HTML via render_html().
    3. Build EmailMessage (multipart/alternative: text/plain + text/html).
    4. Set From, To, Cc, Subject, In-Reply-To, References, Message-ID.
    5. subprocess.run(["gmi", "send", "-t"], input=message.as_bytes(), check=True).
    6. On success, call cleanup_draft(draft).

    Raises:
        SendError: If pandoc or gmi exits non-zero.
    """
    # Re-parse so any user edits to the draft file are picked up.
    if draft.cache_path.exists():
        draft = _parse_draft(draft.cache_path)

    html_body = render_html(draft.body_markdown)

    msg = email.message.EmailMessage()
    msg["From"] = draft.from_
    msg["To"] = ", ".join(draft.to)
    if draft.cc:
        msg["Cc"] = ", ".join(draft.cc)
    msg["Subject"] = draft.subject
    if draft.in_reply_to:
        msg["In-Reply-To"] = draft.in_reply_to
        msg["References"] = draft.in_reply_to
    msg["Message-ID"] = email.utils.make_msgid(domain="phyrax.local")

    msg.set_content(draft.body_markdown, subtype="plain")
    msg.add_alternative(html_body, subtype="html")

    try:
        subprocess.run(
            ["gmi", "send", "-t"],
            input=msg.as_bytes(),
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SendError(f"gmi send failed: {exc.stderr.decode()}") from exc

    cleanup_draft(draft)


def preview_in_browser(html_body: str) -> None:
    """Write HTML to a NamedTemporaryFile and open it in the default browser."""
    with tempfile.NamedTemporaryFile(
        suffix=".html", mode="w", encoding="utf-8", delete=False
    ) as fh:
        fh.write(html_body)
        path = fh.name
    subprocess.run(["xdg-open", path], check=False)
