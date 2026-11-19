"""Human-readable output for tool payloads (ported from BootUI's TextRenderer)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TextIO, TypeGuard

_MAX_CELL_WIDTH = 60


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _is_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _style(text: str, code: str, color: bool) -> str:
    return f"\x1b[{code}m{text}\x1b[0m" if color else text


def _safe(text: str) -> str:
    return "".join(" " if ord(char) < 32 or 0x7F <= ord(char) <= 0x9F else char for char in text)


def _scalar(value: object, color: bool) -> str:
    if value is None:
        return _style("-", "2", color)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if _is_mapping(value):
        return "{}"
    if _is_list(value):
        return "[]"
    return _safe(str(value))


def _table_columns(items: list[object]) -> tuple[list[Mapping[str, object]], list[str]]:
    rows = [item for item in items if _is_mapping(item) and bool(item)]
    if not items or len(rows) != len(items):
        return [], []
    columns = list(dict.fromkeys(str(key) for row in rows for key in row))
    if len(columns) > 8 or any(isinstance(value, (Mapping, list)) for row in rows for value in row.values()):
        return [], []
    return rows, columns


def _render_table(
    rows: list[Mapping[str, object]], columns: list[str], lines: list[str], depth: int, color: bool
) -> None:
    indent = "  " * depth
    cells = [[_scalar(row.get(column), False) for column in columns] for row in rows]
    for row in cells:
        for index, cell in enumerate(row):
            if len(cell) > _MAX_CELL_WIDTH:
                row[index] = cell[: _MAX_CELL_WIDTH - 1] + "…"
    headers = [_safe(column) for column in columns]
    widths = [max(len(headers[i]), *(len(row[i]) for row in cells)) for i in range(len(columns))]
    lines.append(
        indent
        + "  ".join(
            _style(headers[i].ljust(widths[i]) if i < len(columns) - 1 else headers[i], "1", color)
            for i in range(len(columns))
        )
    )
    lines.append(indent + "  ".join(_style("-" * width, "2", color) for width in widths))
    lines.extend(
        indent + "  ".join(row[i].ljust(widths[i]) if i < len(columns) - 1 else row[i] for i in range(len(columns)))
        for row in cells
    )


def _render_mapping(value: Mapping[str, object], lines: list[str], depth: int, color: bool) -> None:
    indent = "  " * depth
    for raw_name, member in value.items():
        name = _safe(str(raw_name))
        if _is_mapping(member) and member:
            lines.append(indent + _style(name, "1", color))
            _render_mapping(member, lines, depth + 1, color)
        elif _is_list(member) and member:
            lines.append(indent + _style(name, "1", color) + _style(f" ({len(member)})", "2", color))
            _render_array(member, lines, depth + 1, color)
        else:
            lines.append(indent + _style(name, "36", color) + ": " + _scalar(member, color))


def _render_array(value: list[object], lines: list[str], depth: int, color: bool) -> None:
    rows, columns = _table_columns(value)
    if columns:
        _render_table(rows, columns, lines, depth, color)
        return
    indent = "  " * depth
    for member in value:
        if _is_mapping(member):
            lines.append(indent + _style("-", "2", color))
            _render_mapping(member, lines, depth + 1, color)
        elif _is_list(member):
            _render_array(member, lines, depth + 1, color)
        else:
            lines.append(indent + _style("- ", "2", color) + _scalar(member, color))


def _render(value: object, lines: list[str], depth: int, color: bool) -> None:
    if _is_mapping(value):
        _render_mapping(value, lines, depth, color)
    elif _is_list(value):
        _render_array(value, lines, depth, color)
    else:
        lines.append(_scalar(value, color))


def render(value: object, *, color: bool) -> str:
    lines: list[str] = []
    if _is_mapping(value):
        low_footprint = value.get("lowFootprint")
        if _is_mapping(low_footprint) and low_footprint.get("paused") is True:
            lines.append(
                _style("PAUSED by low-footprint mode", "1", color)
                + " - buffered evidence is incomplete; sharpit low-footprint disable resumes recording."
            )
        elif _is_mapping(low_footprint) and low_footprint.get("active") is True:
            lines.append(
                _style("Low-footprint mode active", "1", color)
                + " - relevant capture is not known to be paused; inspect lowFootprint warnings."
            )
    _render(value, lines, 0, color)
    return "\n".join(lines)


def write(stream: TextIO, text: str) -> None:
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        replacement = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        stream.write(replacement)


def write_json(stream: TextIO, text: str) -> None:
    """Keep machine-readable output UTF-8 even when an injected stream has another encoding."""
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
    else:
        stream.write(text)
