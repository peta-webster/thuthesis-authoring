#!/usr/bin/env python3
"""Small, dependency-free BibTeX parser used by bibliography quality gates.

The parser intentionally implements only the syntax needed to identify entries
and their fields.  It nevertheless understands nested braced values, quoted
values containing braces, ``#`` concatenation, and both brace- and
parenthesis-delimited entries.  That is enough to avoid the false positives and
silent omissions caused by the former entry-key regular expression without
adding a runtime dependency to the skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BibEntry:
    """A parsed BibTeX entry."""

    entry_type: str
    key: str
    fields: dict[str, str]
    source: str
    line: int
    column: int


class BibSyntaxError(ValueError):
    """A BibTeX syntax error with a stable source location."""

    def __init__(self, message: str, index: int, text: str):
        super().__init__(message)
        self.message = message
        self.index = index
        self.line = text.count("\n", 0, index) + 1
        last_newline = text.rfind("\n", 0, index)
        self.column = index - last_newline


def _is_escaped(text: str, index: int) -> bool:
    """Return whether the character at *index* has an odd backslash prefix."""

    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


class _Parser:
    def __init__(self, text: str, source: str):
        self.text = text
        self.source = source
        self.length = len(text)
        self.index = 0
        self.last_entry_type: Optional[str] = None

    def _error(self, message: str, index: Optional[int] = None) -> BibSyntaxError:
        return BibSyntaxError(message, self.index if index is None else index, self.text)

    def _skip_space_and_comments(self) -> None:
        while self.index < self.length:
            if self.text[self.index].isspace():
                self.index += 1
                continue
            if self.text[self.index] == "%":
                newline = self.text.find("\n", self.index + 1)
                self.index = self.length if newline < 0 else newline + 1
                continue
            break

    def _read_identifier(self) -> str:
        start = self.index
        while self.index < self.length:
            char = self.text[self.index]
            if char.isalnum() or char in "_-:./":
                self.index += 1
            else:
                break
        return self.text[start:self.index]

    def _read_braced_value(self) -> str:
        if self.index >= self.length or self.text[self.index] != "{":
            raise self._error("expected a braced value")
        start = self.index + 1
        self.index += 1
        depth = 1
        while self.index < self.length:
            char = self.text[self.index]
            if char == "{" and not _is_escaped(self.text, self.index):
                depth += 1
            elif char == "}" and not _is_escaped(self.text, self.index):
                depth -= 1
                if depth == 0:
                    value = self.text[start:self.index]
                    self.index += 1
                    return value
            self.index += 1
        raise self._error("unterminated braced value", start - 1)

    def _read_quoted_value(self) -> str:
        if self.index >= self.length or self.text[self.index] != '"':
            raise self._error("expected a quoted value")
        start = self.index + 1
        self.index += 1
        brace_depth = 0
        while self.index < self.length:
            char = self.text[self.index]
            if char == "{" and not _is_escaped(self.text, self.index):
                brace_depth += 1
            elif char == "}" and not _is_escaped(self.text, self.index):
                if brace_depth == 0:
                    raise self._error("unmatched closing brace in quoted value")
                brace_depth -= 1
            elif char == '"' and brace_depth == 0 and not _is_escaped(self.text, self.index):
                value = self.text[start:self.index]
                self.index += 1
                return value
            self.index += 1
        raise self._error("unterminated quoted value", start - 1)

    def _read_bare_value(self, outer_close: str) -> str:
        start = self.index
        while self.index < self.length:
            char = self.text[self.index]
            if char.isspace() or char in (",", "#", outer_close):
                break
            self.index += 1
        if self.index == start:
            raise self._error("expected a BibTeX field value")
        return self.text[start:self.index]

    def _read_value(self, outer_close: str) -> str:
        atoms: list[str] = []
        while True:
            self._skip_space_and_comments()
            if self.index >= self.length:
                raise self._error("unterminated BibTeX field value")
            char = self.text[self.index]
            if char == "{":
                atoms.append(self._read_braced_value())
            elif char == '"':
                atoms.append(self._read_quoted_value())
            else:
                atoms.append(self._read_bare_value(outer_close))
            self._skip_space_and_comments()
            if self.index < self.length and self.text[self.index] == "#":
                self.index += 1
                continue
            break
        return "".join(atoms)

    def _skip_balanced_container(self, outer_open: str, outer_close: str, start: int) -> None:
        depth = 1
        in_quote = False
        while self.index < self.length:
            char = self.text[self.index]
            if char == '"' and not _is_escaped(self.text, self.index):
                in_quote = not in_quote
            elif not in_quote:
                if char == outer_open and not _is_escaped(self.text, self.index):
                    depth += 1
                elif char == outer_close and not _is_escaped(self.text, self.index):
                    depth -= 1
                    self.index += 1
                    if depth == 0:
                        return
                    continue
            self.index += 1
        raise self._error("unterminated BibTeX directive", start)

    def _read_entry(self) -> Optional[BibEntry]:
        at_index = self.index
        self.index += 1
        self._skip_space_and_comments()
        entry_type = self._read_identifier().lower()
        self.last_entry_type = entry_type
        if not entry_type:
            raise self._error("expected an entry type after '@'", at_index)
        self._skip_space_and_comments()
        if self.index >= self.length or self.text[self.index] not in "{(":
            if entry_type == "comment":
                newline = self.text.find("\n", self.index)
                self.index = self.length if newline < 0 else newline + 1
                return None
            raise self._error("expected '{' or '(' after the entry type")

        outer_open = self.text[self.index]
        outer_close = "}" if outer_open == "{" else ")"
        self.index += 1

        if entry_type in {"comment", "preamble", "string"}:
            self._skip_balanced_container(outer_open, outer_close, at_index)
            return None

        self._skip_space_and_comments()
        key_start = self.index
        while self.index < self.length and self.text[self.index] not in (",", outer_close):
            self.index += 1
        if self.index >= self.length:
            raise self._error("unterminated BibTeX entry", at_index)
        if self.text[self.index] == outer_close:
            raise self._error("entry is missing the comma after its citation key", self.index)
        key = self.text[key_start:self.index].strip()
        if not key:
            raise self._error("entry has an empty citation key", key_start)
        if any(char.isspace() for char in key):
            raise self._error("citation key must not contain whitespace", key_start)
        self.index += 1

        fields: dict[str, str] = {}
        while True:
            self._skip_space_and_comments()
            while self.index < self.length and self.text[self.index] == ",":
                self.index += 1
                self._skip_space_and_comments()
            if self.index >= self.length:
                raise self._error("unterminated BibTeX entry", at_index)
            if self.text[self.index] == outer_close:
                self.index += 1
                break

            field_start = self.index
            field_name = self._read_identifier().lower()
            if not field_name:
                raise self._error("expected a BibTeX field name", field_start)
            self._skip_space_and_comments()
            if self.index >= self.length or self.text[self.index] != "=":
                raise self._error("expected '=' after the BibTeX field name")
            self.index += 1
            value = self._read_value(outer_close)
            fields[field_name] = value
            self._skip_space_and_comments()
            if self.index < self.length and self.text[self.index] == ",":
                self.index += 1
            elif self.index < self.length and self.text[self.index] == outer_close:
                continue
            else:
                raise self._error("expected ',' or the end of the BibTeX entry")

        line = self.text.count("\n", 0, at_index) + 1
        last_newline = self.text.rfind("\n", 0, at_index)
        column = at_index - last_newline
        return BibEntry(entry_type, key, fields, self.source, line, column)

    def parse(self) -> tuple[list[BibEntry], list[dict[str, object]]]:
        entries: list[BibEntry] = []
        errors: list[dict[str, object]] = []
        while self.index < self.length:
            self._skip_space_and_comments()
            if self.index >= self.length:
                break
            next_at = self.text.find("@", self.index)
            if next_at < 0:
                break
            self.index = next_at
            try:
                entry = self._read_entry()
            except BibSyntaxError as exc:
                errors.append({
                    "message": exc.message,
                    "line": exc.line,
                    "column": exc.column,
                })
                break
            if entry is not None:
                entries.append(entry)
        return entries, errors


def parse_bibtex(text: str, source: str = "<memory>") -> tuple[list[BibEntry], list[dict[str, object]]]:
    """Parse BibTeX *text*, returning entries and structured syntax errors."""

    return _Parser(text, source).parse()


def parse_bibtex_strict(
    text: str,
    source: str = "<memory>",
    *,
    reject_directives: bool = False,
) -> tuple[list[BibEntry], list[dict[str, object]]]:
    """Parse a complete BibTeX stream without silently ignoring other text.

    ``parse_bibtex`` is intentionally tolerant of prose surrounding entries for
    compatibility with existing databases.  Append-only validation needs a
    stricter boundary: every non-comment token must be a complete entry, and
    generated suffixes must not introduce executable BibTeX directives.
    """

    parser = _Parser(text, source)
    entries: list[BibEntry] = []
    errors: list[dict[str, object]] = []
    while parser.index < parser.length:
        parser._skip_space_and_comments()
        if parser.index >= parser.length:
            break
        if parser.text[parser.index] != "@":
            error = parser._error("unexpected non-comment text outside a BibTeX entry")
            errors.append({"message": error.message, "line": error.line, "column": error.column})
            break
        try:
            entry = parser._read_entry()
        except BibSyntaxError as exc:
            errors.append({"message": exc.message, "line": exc.line, "column": exc.column})
            break
        if entry is not None:
            entries.append(entry)
        elif reject_directives:
            errors.append({
                "message": (
                    "generated additions must contain entries only; "
                    f"@{parser.last_entry_type or 'unknown'} directives are not allowed"
                ),
                "line": parser.text.count("\n", 0, parser.index) + 1,
                "column": 1,
            })
    return entries, errors
