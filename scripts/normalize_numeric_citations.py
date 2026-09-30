#!/usr/bin/env python3
"""Normalize numeric citation markers into LaTeX citation commands."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

from _atomic_write import atomic_write_text, validate_in_place_target
from _markdown_syntax import markdown_code_mask, scan_markdown_math


FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
CLOSE_FOR_OPEN = {"[": "]", "［": "］", "【": "】"}
MARKER_RE = re.compile(r"(?<!\\)([\[［【])([0-9０-９\s,，、;；\-－–—~～至]+)([\]］】])")
REFERENCE_ITEM_RE = re.compile(
    r"^\s*[\[［【]\s*[0-9０-９]+\s*[\]］】]"
    r"(?:\s+\S+|(?=[A-Z][A-Za-z'’-]{1,80}\.)\S+)"
)
SEPARATOR_RE = re.compile(r"[,，、;；]")
RANGE_RE = re.compile(r"^(\d+)\s*(?:-|－|–|—|~|～|至)\s*(\d+)$")
PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9:_-]*$")


def normalize_digits(value: str) -> str:
    return value.translate(FULLWIDTH_DIGITS)


def parse_numeric_citation_items(
    value: str,
    max_range: int = 50,
    max_reference_number: int = 999,
) -> Optional[list[int]]:
    normalized = normalize_digits(value)
    items: list[int] = []
    seen = set()

    for part in SEPARATOR_RE.split(normalized):
        token = part.strip()
        if not token:
            continue
        range_match = RANGE_RE.fullmatch(token)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if (
                start <= 0
                or end > max_reference_number
                or end < start
                or end - start + 1 > max_range
            ):
                return None
            numbers = range(start, end + 1)
        elif re.fullmatch(r"\d+", token):
            number = int(token)
            if number <= 0 or number > max_reference_number:
                return None
            numbers = [number]
        else:
            return None
        for number in numbers:
            if number not in seen:
                items.append(number)
                seen.add(number)

    return items if items else None


def normalize_numeric_citations_with_count(
    text: str,
    key_prefix: str,
    max_range: int = 50,
    max_reference_number: int = 999,
) -> Tuple[str, int]:
    if not PREFIX_RE.fullmatch(key_prefix):
        raise ValueError("key_prefix must start with a letter and contain only letters, digits, colon, underscore, or hyphen")

    # Scan the whole source so display math and code spanning lines remain
    # protected even while replacements are applied one physical line at a time.
    eligible = markdown_code_mask(text)
    math_spans, _ = scan_markdown_math(text)
    for span in math_spans:
        eligible[span.start:span.end] = [False] * (span.end - span.start)

    count = 0
    line_offset = 0

    def repl(match: re.Match) -> str:
        nonlocal count
        if not all(eligible[line_offset + match.start():line_offset + match.end()]):
            return match.group(0)
        opener, content, closer = match.groups()
        if CLOSE_FOR_OPEN.get(opener) != closer:
            return match.group(0)
        numbers = parse_numeric_citation_items(
            content,
            max_range=max_range,
            max_reference_number=max_reference_number,
        )
        if not numbers:
            return match.group(0)
        count += 1
        keys = ",".join(f"{key_prefix}{number}" for number in numbers)
        return r"\cite{" + keys + "}"

    normalized_lines = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        newline = line[len(body):]
        if REFERENCE_ITEM_RE.match(body):
            normalized_lines.append(line)
        else:
            normalized_lines.append(MARKER_RE.sub(repl, body) + newline)
        line_offset += len(line)
    return "".join(normalized_lines), count


def normalize_numeric_citations(
    text: str,
    key_prefix: str,
    max_range: int = 50,
    max_reference_number: int = 999,
) -> str:
    normalized, _ = normalize_numeric_citations_with_count(
        text,
        key_prefix=key_prefix,
        max_range=max_range,
        max_reference_number=max_reference_number,
    )
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="source", help="Citation key prefix, for example aitokenomics.")
    parser.add_argument("--max-range", type=int, default=50, help="Maximum citation range expansion length.")
    parser.add_argument(
        "--max-reference-number",
        type=int,
        default=999,
        help="Largest plausible bibliography number (default: 999).",
    )
    parser.add_argument("--text", help="Normalize this text and print the converted text.")
    parser.add_argument("--in-place", action="store_true", help="Rewrite files in place.")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    if args.max_range <= 0 or args.max_reference_number <= 0:
        print(json.dumps({"ok": False, "error": "range and reference-number limits must be greater than zero"}, ensure_ascii=False, indent=2))
        return 1

    try:
        if args.text is not None:
            print(normalize_numeric_citations(
                args.text,
                key_prefix=args.prefix,
                max_range=args.max_range,
                max_reference_number=args.max_reference_number,
            ))
            return 0

        if not args.files:
            source = sys.stdin.read()
            print(normalize_numeric_citations(
                source,
                key_prefix=args.prefix,
                max_range=args.max_range,
                max_reference_number=args.max_reference_number,
            ), end="")
            return 0

        operations = []
        for item in args.files:
            path = Path(item)
            if args.in_place:
                validate_in_place_target(path)
            original = path.read_text(encoding="utf-8")
            normalized, count = normalize_numeric_citations_with_count(
                original,
                key_prefix=args.prefix,
                max_range=args.max_range,
                max_reference_number=args.max_reference_number,
            )
            operations.append((path, original, normalized, count))

        results = []
        for path, original, normalized, count in operations:
            if args.in_place and normalized != original:
                atomic_write_text(path, normalized)
            results.append({"file": str(path), "changed": normalized != original, "replacements": count})
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
