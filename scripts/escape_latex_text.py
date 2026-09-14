#!/usr/bin/env python3
"""Escape plain source text so it is safe to paste into a LaTeX document.

Source material (Word paragraphs, Markdown prose, pasted notes) regularly
contains characters LaTeX treats as syntax. An unescaped `%` silently comments
out the rest of the line and a bare `_` is a fatal error outside math mode, so
prose must be escaped before it reaches `data/*.tex`.

Use `--math-aware` when the text may contain `$...$` or `$$...$$` spans that
should stay as real math instead of being escaped into literal dollar signs.
"""

from __future__ import annotations

import argparse
import re
import sys

from _markdown_syntax import transform_outside_math

# Substituted in a single pass so the backslash rule cannot re-escape the
# braces introduced by its own replacement.
_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_ESCAPE_RE = re.compile("|".join(re.escape(char) for char in _ESCAPES))


def escape_latex(text: str) -> str:
    """Escape every LaTeX special character in plain text."""
    return _ESCAPE_RE.sub(lambda match: _ESCAPES[match.group(0)], text)


def escape_latex_preserving_math(text: str) -> str:
    r"""Escape Markdown prose while preserving balanced dollar math.

    The shared scanner understands escaped dollars, code, and line boundaries.
    Unclosed delimiters are therefore left in prose and safely become ``\$``.
    """
    return transform_outside_math(text, _escape_markdown_prose)


_MD_ESCAPABLE = set("\\`*_{}[]()#+-.!$|~^<>")


def _escape_markdown_prose(text: str) -> str:
    """Escape a prose-only region, consuming Markdown backslash escapes."""
    out: list[str] = []
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if char == "\\" and index + 1 < length and text[index + 1] in _MD_ESCAPABLE:
            out.append(escape_latex(text[index + 1]))
            index += 2
            continue
        out.append(escape_latex(char))
        index += 1

    return "".join(out)


def escape_markdown_text(text: str) -> str:
    """Escape Markdown prose for LaTeX while preserving balanced math."""
    return transform_outside_math(text, _escape_markdown_prose)


def escape_bib_value(text: str) -> str:
    """Escape a BibTeX field value.

    Entries are emitted as `title = {{...}}`, so an unbalanced brace from the
    source text would terminate the field early and corrupt the entry.
    """
    return escape_latex(text.replace("*", ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", help="Escape this string instead of reading stdin.")
    parser.add_argument(
        "--math-aware",
        action="store_true",
        help="Preserve $...$ and $$...$$ spans instead of escaping them.",
    )
    parser.add_argument(
        "--bib",
        action="store_true",
        help="Escape as a BibTeX field value (also drops Markdown emphasis asterisks).",
    )
    args = parser.parse_args()

    source = args.text if args.text is not None else sys.stdin.read()
    if args.bib:
        print(escape_bib_value(source), end="" if args.text is None else "\n")
    elif args.math_aware:
        print(escape_latex_preserving_math(source), end="" if args.text is None else "\n")
    else:
        print(escape_latex(source), end="" if args.text is None else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
