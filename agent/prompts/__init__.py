"""Jinja2-based prompt loader.

Prompts live in ``templates/`` as ``{name}.system.jinja2`` and
``{name}.user.jinja2`` so system and user messages are versioned separately and
never hardcoded in Python. ``StrictUndefined`` makes a missing variable a loud
error instead of a silent empty string.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=StrictUndefined,
        autoescape=False,  # prompts are plain text, not HTML
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(name: str, **context) -> tuple[str, str]:
    """Render ``{name}`` into a ``(system_prompt, user_prompt)`` pair."""
    env = _env()
    system = env.get_template(f"{name}.system.jinja2").render(**context)
    user = env.get_template(f"{name}.user.jinja2").render(**context)
    return system.strip(), user.strip()
