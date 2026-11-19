"""Sanitising for Mermaid output (SPEC §5.5, §9.1)."""

import re

_RESERVED = {
    "title",
    "rel",
    "end",
    "default",
    "boundary",
    "component",
    "container",
    "system",
    "person",
}


def make_id(name: str, used: set[str]) -> str:
    """Unique Mermaid-safe id ([A-Za-z0-9_]), registered in `used`."""
    base = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_") or "x"
    if base[0].isdigit() or base.lower() in _RESERVED:
        base = f"n_{base}"
    candidate, i = base, 2
    while candidate in used:
        candidate, i = f"{base}_{i}", i + 1
    used.add(candidate)
    return candidate


def label(text: str | None, limit: int = 120) -> str:
    """Make free text safe inside a double-quoted Mermaid string."""
    s = re.sub(r"\s+", " ", (text or "")).strip()
    s = s.replace('"', "'").replace("`", "'").replace("\\", "/")
    s = s.replace("{", "(").replace("}", ")").replace("%%", "%")
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"
