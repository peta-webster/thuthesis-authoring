#!/usr/bin/env python3
"""Convert Markdown pipe tables into ThuThesis three-line (booktabs) tables.

A Markdown pipe table has an unambiguous structure -- the delimiter row fixes
the column count and alignment, and there are no merged cells -- so the grid
converts deterministically. What Markdown cannot supply is a caption, so the
generated float carries a `[TODO: ...]` caption for the user to fill in rather
than an invented one.

Left as-is by design: Word tables (see references/source-ingestion.md), which
can carry merged cells and nested content that no deterministic mapping
handles.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _atomic_write import atomic_write_text, validate_in_place_target
from _markdown_syntax import (
    CAPTION_RE,
    ROW_RE,
    parse_pipe_alignments,
    scan_pipe_tables,
    split_pipe_row,
)
from escape_latex_text import escape_markdown_text

# Retained as a module-level compatibility name.  Recognition itself lives in
# the shared parser and requires at least three hyphens per delimiter cell.
DELIMITER_RE = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
# Beyond this many columns a full-size font overflows the text block.
SMALL_FONT_MIN_COLUMNS = 5
# Below this many columns the cells are short enough for natural widths.
FIXED_WIDTH_MIN_COLUMNS = 4
LABEL_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9:_-]*$")
MAX_LABEL_PREFIX_LENGTH = 64


def validate_label_prefix(value: str) -> None:
    if len(value) > MAX_LABEL_PREFIX_LENGTH or not LABEL_PREFIX_RE.fullmatch(value):
        raise ValueError(
            "label prefix must start with a letter, contain only letters, digits, colon, underscore, or hyphen, and be at most 64 characters"
        )


def split_row(line: str) -> list[str]:
    """Compatibility wrapper around the shared pipe-row parser."""
    return split_pipe_row(line)


def parse_alignments(line: str) -> list[str]:
    """Return v1-style alignment hints using the shared row splitter.

    Historically this public helper accepted any pipe row, not just a valid
    Markdown delimiter.  Table recognition now uses the strict shared
    ``parse_pipe_alignments`` implementation, while this wrapper retains the
    original boundary behaviour for callers that imported it directly.
    """
    alignments: list[str] = []
    for cell in split_pipe_row(line):
        left = cell.startswith(":")
        right = cell.endswith(":")
        if left and right:
            alignments.append("c")
        elif right:
            alignments.append("r")
        else:
            alignments.append("l")
    return alignments


def column_spec(alignments: list[str]) -> str:
    count = len(alignments)
    if count < FIXED_WIDTH_MIN_COLUMNS:
        return "".join(alignments)
    # Fixed widths that exactly fill \linewidth once tabcolsep padding is
    # accounted for, so wide Chinese tables wrap instead of running off page.
    width = rf"\dimexpr\linewidth/{count}-2\tabcolsep\relax"
    prefix = {"l": r">{\raggedright\arraybackslash}", "c": r">{\centering\arraybackslash}", "r": r">{\raggedleft\arraybackslash}"}
    return "".join(f"{prefix[a]}p{{{width}}}" for a in alignments)


def render_table(
    header: list[str],
    rows: list[list[str]],
    alignments: list[str],
    label: str,
    caption: str = "",
) -> str:
    def cells(values: list[str]) -> str:
        if len(values) != len(alignments):
            raise ValueError("table row width does not match the delimiter row")
        return " & ".join(escape_markdown_text(value) for value in values)

    small = r"  \small" + "\n" if len(alignments) >= SMALL_FONT_MIN_COLUMNS else ""
    body = "\n".join(f"    {cells(row)} \\\\" for row in rows)
    caption_text = escape_markdown_text(caption).rstrip("。.") if caption else "[TODO: 补充表标题]"
    return (
        "\\begin{table}[htbp]\n"
        "  \\centering\n"
        f"  \\caption{{{caption_text}}}\n"
        f"  \\label{{tab:{label}}}\n"
        f"{small}"
        f"  \\begin{{tabular}}{{{column_spec(alignments)}}}\n"
        "    \\toprule\n"
        f"    {cells(header)} \\\\\n"
        "    \\midrule\n"
        f"{body}\n"
        "    \\bottomrule\n"
        "  \\end{tabular}\n"
        "\\end{table}"
    )


def convert_markdown_tables(text: str, label_prefix: str = "src", start_index: int = 0) -> tuple[str, int]:
    """Convert every pipe table in `text`.

    `start_index` continues the label numbering across separate calls, so a
    caller converting one chapter at a time does not emit `tab:src1` three
    times over. The returned count is the last label index used, ready to be
    passed straight back in as the next `start_index`.
    """
    validate_label_prefix(label_prefix)
    lines = text.splitlines()
    out: list[str] = []
    index = 0
    count = start_index
    tables = {table.start_index: table for table in scan_pipe_tables(text)}

    while index < len(lines):
        table = tables.get(index)
        if table is None:
            out.append(lines[index])
            index += 1
            continue

        if not table.valid:
            out.extend(lines[table.start_index:table.end_index + 1])
            index = table.end_index + 1
            continue

        # Adopt a bold caption line sitting just above the table, so it becomes
        # the float's caption instead of a stray bold paragraph beside it.
        caption = ""
        trailing_blanks = 0
        while out and not out[-1].strip():
            out.pop()
            trailing_blanks += 1
        if out:
            caption_match = CAPTION_RE.match(out[-1])
            if caption_match:
                caption = caption_match.group(1)
                out.pop()
            else:
                out.extend([""] * trailing_blanks)
        else:
            out.extend([""] * trailing_blanks)

        count += 1
        out.append(render_table(
            table.header,
            table.rows,
            table.alignments,
            f"{label_prefix}{count}",
            caption,
        ))
        index = table.end_index + 1

    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", help="Convert this string and print the result.")
    parser.add_argument("--label-prefix", default="src", help="Prefix for generated table labels.")
    parser.add_argument("--in-place", action="store_true", help="Rewrite files in place.")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    try:
        validate_label_prefix(args.label_prefix)
        if args.text is not None:
            converted, _ = convert_markdown_tables(args.text, label_prefix=args.label_prefix)
            print(converted)
            return 0

        if not args.files:
            converted, _ = convert_markdown_tables(sys.stdin.read(), label_prefix=args.label_prefix)
            print(converted, end="")
            return 0

        operations = []
        next_index = 0
        for item in args.files:
            path = Path(item)
            if args.in_place:
                validate_in_place_target(path)
            original = path.read_text(encoding="utf-8")
            previous_index = next_index
            converted, next_index = convert_markdown_tables(
                original,
                label_prefix=args.label_prefix,
                start_index=next_index,
            )
            operations.append((path, original, converted, next_index - previous_index))

        results = []
        for path, original, converted, converted_count in operations:
            if args.in_place and converted != original:
                atomic_write_text(path, converted)
            results.append({
                "file": str(path),
                "tables_converted": converted_count,
                "changed": converted != original,
            })
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
