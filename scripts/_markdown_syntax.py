#!/usr/bin/env python3
"""Shared, dependency-free Markdown syntax scanners used by skill helpers.

The module intentionally recognises only the two source constructs that the
helpers can handle deterministically: dollar-delimited math and pipe tables
with optional outer delimiters.  It is a scanner rather than a Markdown
renderer.  In particular,
it preserves source text and reports malformed constructs instead of guessing
how they should be repaired.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from typing import Callable, Optional


FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
ROW_RE = re.compile(r"^\s*\|(.*)\|\s*$")
DELIMITER_CELL_RE = re.compile(r"^:?-{3,}:?$")
DELIMITER_LIKE_RE = re.compile(r"^:?-+:?$")
CAPTION_RE = re.compile(
    r"^\s*\*\*\s*(?:表|Table|TABLE)\s*[0-9０-９]*\s*[:：.]?\s*(.+?)\s*\*\*\s*$"
)


def _line_starts(text: str) -> list[int]:
    starts = [0]
    starts.extend(index + 1 for index, char in enumerate(text) if char == "\n")
    return starts


def _line_number(starts: list[int], offset: int) -> int:
    return bisect.bisect_right(starts, max(0, offset))


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _can_open_inline_math(text: str, index: int) -> bool:
    """Apply Pandoc's non-whitespace rule to an opening dollar."""
    return index + 1 < len(text) and not text[index + 1].isspace() and text[index + 1] != "$"


def _can_close_inline_math(text: str, index: int) -> bool:
    """Apply Pandoc's closing-dollar rules, including the price safeguard."""
    if index <= 0 or text[index - 1].isspace() or text[index - 1] == "$":
        return False
    return index + 1 >= len(text) or not text[index + 1].isdigit()


def markdown_fenced_lines(text: str) -> set[int]:
    """Return zero-based physical lines belonging to fenced code blocks."""
    fenced: set[int] = set()
    fence_char: Optional[str] = None
    fence_length = 0

    for line_index, line in enumerate(text.splitlines(keepends=True)):
        content = line.rstrip("\r\n")
        fence = FENCE_RE.match(content)
        if fence_char is not None:
            fenced.add(line_index)
            marker = fence.group(1) if fence else ""
            closing_remainder = content[fence.end():] if fence else ""
            if (
                marker
                and marker[0] == fence_char
                and len(marker) >= fence_length
                and not closing_remainder.strip()
            ):
                fence_char = None
                fence_length = 0
            continue

        if fence:
            marker = fence.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            fenced.add(line_index)

    return fenced


def markdown_code_mask(text: str) -> list[bool]:
    """Return a mask whose false positions are fenced or inline code.

    Fenced code follows CommonMark's backtick/tilde opening rules closely
    enough for ingestion.  Backtick code spans may cross physical lines and
    close only on a run of exactly the opening length.  An unmatched run is
    left eligible so it cannot hide the remainder of the document.
    """
    eligible = [True] * len(text)
    fenced_lines = markdown_fenced_lines(text)
    offset = 0
    for line_index, line in enumerate(text.splitlines(keepends=True)):
        if line_index in fenced_lines:
            for index in range(offset, offset + len(line)):
                eligible[index] = False
        offset += len(line)

    cursor = 0
    while cursor < len(text):
        if not eligible[cursor] or text[cursor] != "`" or _is_escaped(text, cursor):
            cursor += 1
            continue
        run_end = cursor + 1
        while run_end < len(text) and eligible[run_end] and text[run_end] == "`":
            run_end += 1
        run_length = run_end - cursor
        close_start = run_end
        close_end = -1
        while close_start < len(text):
            # A fenced block is a hard barrier: inline code cannot begin on
            # one side and close on the other.
            if not eligible[close_start]:
                break
            if text[close_start] != "`" or _is_escaped(text, close_start):
                close_start += 1
                continue
            candidate_end = close_start + 1
            while (
                candidate_end < len(text)
                and eligible[candidate_end]
                and text[candidate_end] == "`"
            ):
                candidate_end += 1
            if candidate_end - close_start == run_length:
                close_end = candidate_end
                break
            close_start = candidate_end
        if close_end == -1:
            cursor = run_end
            continue
        for index in range(cursor, close_end):
            eligible[index] = False
        cursor = close_end

    return eligible


@dataclass(frozen=True)
class MathSpan:
    kind: str
    start: int
    end: int
    start_line: int
    end_line: int
    text: str

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "start_offset": self.start,
            "end_offset": self.end,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


@dataclass(frozen=True)
class MathIssue:
    kind: str
    start: int
    end: int
    start_line: int
    end_line: int

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "reason_code": "unclosed_markdown_math",
            "start_offset": self.start,
            "end_offset": self.end,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


def scan_markdown_math(text: str) -> tuple[list[MathSpan], list[MathIssue]]:
    r"""Find balanced ``$...$`` and ``$$...$$`` objects outside code.

    Inline math never crosses a physical line.  Display math may cross lines.
    A dollar is a delimiter only when preceded by an even number of
    backslashes, which is what keeps ``\$`` intact inside math.
    """
    eligible = markdown_code_mask(text)
    starts = _line_starts(text)
    spans: list[MathSpan] = []
    issues: list[MathIssue] = []
    length = len(text)
    index = 0

    while index < length:
        if not eligible[index] or text[index] != "$" or _is_escaped(text, index):
            index += 1
            continue

        is_display = (
            index + 1 < length
            and eligible[index + 1]
            and text[index + 1] == "$"
        )
        if not is_display and not _can_open_inline_math(text, index):
            index += 1
            continue
        delimiter_length = 2 if is_display else 1
        cursor = index + delimiter_length
        closing = -1
        rejected_inline_delimiter = -1

        while cursor < length:
            if not is_display and text[cursor] in "\r\n":
                break
            if not eligible[cursor]:
                cursor += 1
                continue
            if text[cursor] != "$" or _is_escaped(text, cursor):
                cursor += 1
                continue
            if is_display:
                if (
                    cursor + 1 < length
                    and eligible[cursor + 1]
                    and text[cursor + 1] == "$"
                ):
                    closing = cursor
                    break
                cursor += 1
                continue
            # A double-dollar token belongs to display syntax and must not be
            # consumed as the closing half of an inline span.
            if cursor + 1 < length and eligible[cursor + 1] and text[cursor + 1] == "$":
                cursor += 2
                continue
            if cursor > index + 1 and _can_close_inline_math(text, cursor):
                closing = cursor
                break
            # Dollar math cannot nest.  Once the next single-dollar token
            # fails Pandoc's closing rules, the current candidate is
            # malformed; do not leap across it and swallow a later valid span.
            rejected_inline_delimiter = cursor
            break

        if closing != -1:
            end = closing + delimiter_length
            spans.append(MathSpan(
                kind="display" if is_display else "inline",
                start=index,
                end=end,
                start_line=_line_number(starts, index),
                end_line=_line_number(starts, end - 1),
                text=text[index:end],
            ))
            index = end
            continue

        line_end = length if is_display else (
            # The rejected dollar is reconsidered as a possible opener below,
            # so keep the malformed range half-open and non-overlapping.
            rejected_inline_delimiter
            if rejected_inline_delimiter != -1
            else min(
                (position for position in (text.find("\n", index), text.find("\r", index)) if position != -1),
                default=length,
            )
        )
        issues.append(MathIssue(
            kind="display" if is_display else "inline",
            start=index,
            end=line_end,
            start_line=_line_number(starts, index),
            end_line=_line_number(starts, max(index, line_end - 1)),
        ))
        # Reconsider a rejected closing dollar as the next possible opener.
        # It is strictly to the right of ``index``, so this cannot loop, and it
        # preserves a valid span after prose such as ``price $5, formula $x$``.
        index = (
            rejected_inline_delimiter
            if rejected_inline_delimiter != -1
            else index + delimiter_length
        )

    return spans, issues


def transform_outside_math(text: str, transform: Callable[[str], str]) -> str:
    """Apply ``transform`` to prose while preserving balanced math verbatim."""
    spans, _ = scan_markdown_math(text)
    out: list[str] = []
    cursor = 0
    for span in spans:
        out.append(transform(text[cursor:span.start]))
        out.append(span.text)
        cursor = span.end
    out.append(transform(text[cursor:]))
    return "".join(out)


def split_pipe_row(line: str) -> list[str]:
    """Split a leading/trailing pipe row, respecting odd escaped pipes."""
    match = ROW_RE.match(line)
    if not match:
        return []
    body = match.group(1)
    cells: list[str] = []
    start = 0
    for index, char in enumerate(body):
        if char != "|" or _is_escaped(body, index):
            continue
        cells.append(body[start:index].strip())
        start = index + 1
    cells.append(body[start:].strip())
    return cells


def parse_markdown_row(line: str) -> list[str]:
    r"""Parse a general pipe-table row with optional outer pipes.

    This is intentionally separate from :func:`split_pipe_row`, whose strict
    leading-and-trailing-pipe behaviour is a v1 compatibility contract.
    Unescaped separators use odd/even backslash parity, so ``\|`` stays in a
    cell while a pipe after two backslashes remains structural.
    """
    value = line.strip()
    if not value:
        return []
    separators = [
        index
        for index, char in enumerate(value)
        if char == "|" and not _is_escaped(value, index)
    ]
    if not separators:
        return []

    leading = separators[0] == 0
    trailing = separators[-1] == len(value) - 1
    start = 1 if leading else 0
    end = len(value) - 1 if trailing else len(value)
    internal = [position for position in separators if start <= position < end]

    # With neither an internal separator nor both outer delimiters there is no
    # unambiguous row.  A one-column ``| value |`` row remains supported.
    if not internal and not (leading and trailing):
        return []

    cells: list[str] = []
    cell_start = start
    for position in internal:
        cells.append(value[cell_start:position].strip())
        cell_start = position + 1
    cells.append(value[cell_start:end].strip())
    return cells


def _parse_table_continuation_row(line: str) -> list[str]:
    """Parse a row after a table has started, including suspicious one-cells."""
    cells = parse_markdown_row(line)
    if cells:
        return cells
    value = line.strip()
    separators = [
        index
        for index, char in enumerate(value)
        if char == "|" and not _is_escaped(value, index)
    ]
    if len(separators) != 1:
        return []
    position = separators[0]
    if position == 0 and len(value) > 1:
        return [value[1:].strip()]
    if position == len(value) - 1 and position > 0:
        return [value[:-1].strip()]
    return []


def parse_pipe_alignments(line: str) -> list[str]:
    cells = parse_markdown_row(line)
    if not cells or any(not DELIMITER_CELL_RE.fullmatch(cell.strip()) for cell in cells):
        return []
    alignments: list[str] = []
    for cell in cells:
        value = cell.strip()
        left = value.startswith(":")
        right = value.endswith(":")
        if left and right:
            alignments.append("c")
        elif right:
            alignments.append("r")
        else:
            alignments.append("l")
    return alignments


def _is_delimiter_like(line: str) -> bool:
    cells = parse_markdown_row(line)
    return bool(cells) and all(DELIMITER_LIKE_RE.fullmatch(cell.strip()) for cell in cells)


TABLE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
TABLE_FOOTNOTE_RE = re.compile(r"\[\^[^\]]+\](?::)?")
TABLE_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\([^)]*\)")
TABLE_REFERENCE_LINK_RE = re.compile(r"\[[^\]\n]+\]\[[^\]\n]*\]")
TABLE_HTML_RE = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")


def _table_cell_markup_view(cell: str) -> str:
    """Blank deterministic math and escaped literals before markup checks."""
    view = list(cell)
    math_spans, _ = scan_markdown_math(cell)
    for span in math_spans:
        for index in range(span.start, span.end):
            view[index] = " "
    for index, char in enumerate(cell):
        if view[index] != " " and _is_escaped(cell, index):
            view[index] = " "
    return "".join(view)


def _has_asterisk_emphasis(view: str) -> bool:
    """Recognise ordinary ``*em*``/``**strong**`` delimiter pairs."""
    index = 0
    while index < len(view):
        if view[index] != "*":
            index += 1
            continue
        run_end = index + 1
        while run_end < len(view) and view[run_end] == "*":
            run_end += 1
        run_length = run_end - index
        if run_end >= len(view) or view[run_end].isspace():
            index = run_end
            continue
        cursor = run_end
        while cursor < len(view):
            if view[cursor] != "*":
                cursor += 1
                continue
            close_end = cursor + 1
            while close_end < len(view) and view[close_end] == "*":
                close_end += 1
            if close_end - cursor == run_length and cursor > run_end and not view[cursor - 1].isspace():
                return True
            cursor = close_end
        index = run_end
    return False


def _has_underscore_emphasis(view: str) -> bool:
    """Recognise underscore emphasis without flagging intraword underscores."""
    index = 0
    while index < len(view):
        if view[index] != "_":
            index += 1
            continue
        run_end = index + 1
        while run_end < len(view) and view[run_end] == "_":
            run_end += 1
        run_length = run_end - index
        previous = view[index - 1] if index else ""
        following = view[run_end] if run_end < len(view) else ""
        can_open = bool(following and not following.isspace()) and not (
            previous.isalnum() and following.isalnum()
        )
        if not can_open:
            index = run_end
            continue
        cursor = run_end
        while cursor < len(view):
            if view[cursor] != "_":
                cursor += 1
                continue
            close_end = cursor + 1
            while close_end < len(view) and view[close_end] == "_":
                close_end += 1
            before_close = view[cursor - 1] if cursor else ""
            after_close = view[close_end] if close_end < len(view) else ""
            can_close = bool(before_close and not before_close.isspace()) and not (
                before_close.isalnum() and after_close.isalnum()
            )
            if close_end - cursor == run_length and can_close:
                return True
            cursor = close_end
        index = run_end
    return False


def unsupported_table_cell_reason(cells: list[list[str]]) -> str:
    """Return a reason code for cell content that is not deterministic."""
    for row in cells:
        for cell in row:
            view = _table_cell_markup_view(cell)
            if "`" in view:
                return "markdown_table_code_requires_review"
            if TABLE_IMAGE_RE.search(view):
                return "markdown_table_image_requires_review"
            if TABLE_FOOTNOTE_RE.search(view):
                return "markdown_table_footnote_requires_review"
            if TABLE_REFERENCE_LINK_RE.search(view):
                return "markdown_table_reference_link_requires_review"
            if TABLE_LINK_RE.search(view):
                return "markdown_table_link_requires_review"
            if TABLE_HTML_RE.search(view):
                return "markdown_table_html_requires_review"
            if _has_asterisk_emphasis(view) or _has_underscore_emphasis(view):
                return "markdown_table_emphasis_requires_review"
    return ""


@dataclass(frozen=True)
class PipeTable:
    start_index: int
    end_index: int
    start_line: int
    end_line: int
    header: list[str]
    alignments: list[str]
    rows: list[list[str]]
    source_text: str
    valid: bool
    reason_code: str
    caption: str = ""
    caption_line: Optional[int] = None

    def as_candidate_dict(self) -> dict:
        return {
            "type": "markdown_pipe_table",
            "start_line": self.start_line,
            "end_line": self.end_line,
            "caption_line": self.caption_line,
            "caption": self.caption,
            "header": self.header,
            "alignments": self.alignments,
            "rows": self.rows,
            "source_text": self.source_text,
            "recommended_tool": "scripts/convert_markdown_tables.py",
        }


def scan_pipe_tables(text: str) -> list[PipeTable]:
    """Recognise valid and malformed Markdown pipe tables as whole regions."""
    lines = text.splitlines()
    code_mask = markdown_code_mask(text)
    line_offsets = _line_starts(text)

    def line_is_code(line_index: int) -> bool:
        if line_index >= len(line_offsets):
            return False
        start = line_offsets[line_index]
        end = start + len(lines[line_index])
        return end > start and not any(code_mask[start:end])

    tables: list[PipeTable] = []
    index = 0
    while index < len(lines):
        if line_is_code(index) or not parse_markdown_row(lines[index]):
            index += 1
            continue

        cursor = index
        while (
            cursor < len(lines)
            and not line_is_code(cursor)
            and _parse_table_continuation_row(lines[cursor])
        ):
            cursor += 1

        # A single pipe-delimited line is more likely prose than a table.
        if cursor - index < 2:
            index = cursor
            continue

        header = parse_markdown_row(lines[index])
        delimiter_line = lines[index + 1]
        alignments = parse_pipe_alignments(delimiter_line)
        rows = [_parse_table_continuation_row(line) for line in lines[index + 2:cursor]]
        reason_code = ""
        if not _is_delimiter_like(delimiter_line):
            reason_code = "missing_markdown_table_delimiter"
        elif not alignments:
            reason_code = "invalid_markdown_table_delimiter"
        elif len(header) != len(alignments):
            reason_code = "markdown_table_header_width_mismatch"
        elif any(len(row) != len(alignments) for row in rows):
            reason_code = "markdown_table_row_width_mismatch"
        else:
            reason_code = unsupported_table_cell_reason([header] + rows)

        caption = ""
        caption_line: Optional[int] = None
        previous = index - 1
        while previous >= 0 and not lines[previous].strip():
            previous -= 1
        if previous >= 0:
            caption_match = CAPTION_RE.match(lines[previous])
            if caption_match:
                caption = caption_match.group(1)
                caption_line = previous + 1

        tables.append(PipeTable(
            start_index=index,
            end_index=cursor - 1,
            start_line=index + 1,
            end_line=cursor,
            header=header,
            alignments=alignments,
            rows=rows,
            source_text="\n".join(lines[index:cursor]),
            valid=not reason_code,
            reason_code=reason_code,
            caption=caption,
            caption_line=caption_line,
        ))
        index = cursor

    return tables
