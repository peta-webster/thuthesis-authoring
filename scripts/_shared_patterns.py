#!/usr/bin/env python3
"""Shared LaTeX parsing patterns for the check_*/extract_*.py scripts.

These regexes previously lived as separate copies in each script and had
drifted (e.g. only one script recognized \\citealp/\\citealt), causing the
checkers to disagree about the same input. Importing from here keeps them
in sync.
"""

from __future__ import annotations

import re

CITE_RE = re.compile(
    r"\\(?:cite|citet|citep|citealp|citealt|parencite|textcite)\*?"
    r"(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]+)\}"
)

SUSPICIOUS_KEY_RE = re.compile(
    r"^(todo|tbd|ref|ref\d+|citation|source|Smith20\d\d|Wang20\d\d|Zhang20\d\d)$",
    re.I,
)

TODO_TOKEN_RE = re.compile(r"TODO")
VALID_TODO_RE = re.compile(r"\[TODO: [^\]]+\]")

LITERAL_ENVIRONMENTS = ("verbatim", "verbatim*", "lstlisting", "lstlisting*", "minted")
VERB_RE = re.compile(r"\\verb\*?(?P<delimiter>[^\w\s])(?P<body>.*?)(?P=delimiter)")


def strip_tex_comments(text: str) -> str:
    """Drop LaTeX line comments, honouring backslash escapes.

    A `%` only starts a comment when it is not escaped. Walking characters
    tracks `\\%` and `\\\\%` correctly, which a plain `(?<!\\)%` lookbehind
    does not.
    """
    lines = []
    for line in text.splitlines():
        escaped = False
        kept = []
        for char in line:
            if escaped:
                kept.append(char)
                escaped = False
            elif char == "\\":
                kept.append(char)
                escaped = True
            elif char == "%":
                break
            else:
                kept.append(char)
        lines.append("".join(kept))
    return "\n".join(lines)


def _mask_preserving_newlines(value: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in value)


def mask_literal_tex_content(text: str) -> str:
    """Hide literal-code content while retaining line numbers and delimiters.

    Braces, citations, TODO strings, and percent signs inside verbatim-like
    environments or ``\\verb`` are literal text, not active LaTeX syntax.
    Keeping the begin/end tokens still lets the environment checker detect an
    unclosed or mismatched literal environment.
    """
    masked = text
    for environment in LITERAL_ENVIRONMENTS:
        escaped = re.escape(environment)
        pattern = re.compile(
            rf"(\\begin\{{{escaped}\}})(.*?)(\\end\{{{escaped}\}})",
            re.S,
        )
        masked = pattern.sub(
            lambda match: match.group(1)
            + _mask_preserving_newlines(match.group(2))
            + match.group(3),
            masked,
        )
    return VERB_RE.sub(
        lambda match: match.group(0)[: match.start("body") - match.start()]
        + _mask_preserving_newlines(match.group("body"))
        + match.group("delimiter"),
        masked,
    )


def prepare_active_tex(text: str) -> str:
    """Return active LaTeX with comments and literal-code contents removed."""
    return strip_tex_comments(mask_literal_tex_content(text))
