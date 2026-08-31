"""Output rendering.

Two audiences, one code path. Humans get compact aligned text; agents get
``--json``. Every command routes through ``emit`` so the ``--json`` flag never
has to be threaded through business logic, and so no command can accidentally
print prose into a JSON stream.
"""

from __future__ import annotations

import json
import shutil
import sys

_JSON = False


def set_json(enabled: bool) -> None:
    global _JSON
    _JSON = bool(enabled)


def json_mode() -> bool:
    return _JSON


def term_width(default: int = 100) -> int:
    return shutil.get_terminal_size((default, 24)).columns


def emit(payload, text_renderer=None) -> None:
    """Print `payload` as JSON, or via `text_renderer` in human mode.

    `text_renderer` receives the payload and either prints, or returns a string
    or an iterable of lines.
    """
    if _JSON:
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return
    if text_renderer is None:
        print(payload)
        return
    result = text_renderer(payload)
    if result is None:
        return
    if isinstance(result, str):
        print(result)
    else:
        for line in result:
            print(line)


def note(message: str) -> None:
    """Human-only commentary. Suppressed in JSON mode to keep stdout parseable."""
    if not _JSON:
        print(message)


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def truncate(text: str, width: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


def table(rows: list[list[str]], headers: list[str] | None = None,
          max_widths: list[int] | None = None) -> list[str]:
    """Render aligned columns, with the last column absorbing leftover width."""
    if not rows:
        return []
    columns = max(len(r) for r in rows)
    grid = [[str(c) if c is not None else "" for c in r] + [""] * (columns - len(r)) for r in rows]
    if headers:
        grid.insert(0, list(headers) + [""] * (columns - len(headers)))

    widths = [max(len(row[i]) for row in grid) for i in range(columns)]
    if max_widths:
        for i, cap in enumerate(max_widths[:columns]):
            if cap:
                widths[i] = min(widths[i], cap)

    # Give the final column whatever the terminal has left over.
    budget = term_width() - (sum(widths[:-1]) + 2 * (columns - 1))
    if columns > 1 and budget > 10:
        widths[-1] = max(widths[-1], budget)

    lines = []
    for index, row in enumerate(grid):
        cells = [truncate(cell, widths[i]).ljust(widths[i]) for i, cell in enumerate(row)]
        lines.append("  ".join(cells).rstrip())
        if headers and index == 0:
            lines.append("  ".join("-" * w for w in widths).rstrip())
    return lines
