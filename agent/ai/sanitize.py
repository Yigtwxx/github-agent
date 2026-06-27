"""Prompt-injection mitigation helpers.

Untrusted text (issue/discussion bodies, file contents, repo metadata) is
wrapped in randomized delimiters so the model can tell DATA from INSTRUCTIONS.
The system guard (see prompt templates) instructs the model never to follow
instructions found between these markers.
"""
from __future__ import annotations

import secrets

# Hard caps so a giant body cannot blow the token budget on its own. The token
# budgeter trims further if needed; these are coarse character-level guards.
MAX_FIELD_CHARS = 12_000


def make_sentinel() -> str:
    """Return a short random nonce for fencing untrusted content."""
    return secrets.token_hex(8)


def cap(text: str | None, max_chars: int = MAX_FIELD_CHARS) -> str:
    """Length-cap a field, appending a marker when truncated."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def fence(content: str | None, sentinel: str, *, max_chars: int = MAX_FIELD_CHARS) -> str:
    """Wrap untrusted ``content`` in randomized markers.

    Any pre-existing ``<<UNTRUSTED`` / ``<<END`` tokens in the content are
    neutralized so a crafted body cannot forge a closing marker and escape the
    fence.
    """
    safe = cap(content, max_chars)
    safe = safe.replace("<<UNTRUSTED", "<<_UNTRUSTED").replace("<<END", "<<_END")
    return f"<<UNTRUSTED_{sentinel}>>\n{safe}\n<<END_{sentinel}>>"
