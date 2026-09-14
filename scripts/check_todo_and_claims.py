#!/usr/bin/env python3
"""Audit TODO markers, suspicious citations, and source-sensitive claims."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _shared_patterns import CITE_RE, SUSPICIOUS_KEY_RE, TODO_TOKEN_RE, VALID_TODO_RE, prepare_active_tex

# Strong claims that need nearby evidence. The English alternatives mirror the
# Chinese ones so a `language=english` thesis gets the same audit; word
# boundaries keep them from firing inside longer words.
CLAIM_RE = re.compile(
    r"(显著|最优|首次|证明了|实验结果表明|大幅提升|优于|领先"
    r"|state-of-the-art|\bSOTA\b"
    r"|\bsignificantly\b|\boutperform\w*|\bsuperior to\b"
    r"|\bthe first (?:to|work|method|study|approach|system)\b"
    r"|\bthe best\b|\boptimal\b"
    r"|\bexperimental results\b|\bprove[sd]?\s+that\b"
    r"|\b(?:substantially|dramatically|considerably)\s+(?:improv|better|outperform)\w*)",
    re.I,
)
EVIDENCE_RE = re.compile(
    r"(\\ref\{|\\autoref\{|表\s*\d|图\s*\d|[Tt]able\s*\d|[Ff]ig(?:ure)?\.?\s*\d"
    r"|\d+(?:\.\d+)?\s*%|\[[0-9,\s]+\]|\[TODO:)"
)
HEADING_RE = re.compile(r"\\(?:chapter|section|subsection|subsubsection)\*?\{")


def line_window(lines: list[str], index: int, radius: int = 1) -> str:
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    return "\n".join(lines[start:end])


def _unescaped_comment_index(line: str) -> int | None:
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "%":
            return index
    return None


def collect_todos_from_text(text: str, path: Path) -> dict[str, object]:
    """Collect every valid TODO, including markers in comments or literal text."""

    active_lines = prepare_active_tex(text).splitlines()
    items: list[dict[str, object]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        active_line = active_lines[line_no - 1] if line_no <= len(active_lines) else ""
        comment_index = _unescaped_comment_index(line)
        for match in VALID_TODO_RE.finditer(line):
            marker = match.group(0)
            active = active_line[match.start():match.end()] == marker
            commented = comment_index is not None and match.start() > comment_index
            items.append({
                "file": str(path),
                "line": line_no,
                "text": marker,
                "active": active,
                "commented": commented,
                "blocking": "BLOCKING:" in marker,
            })
    return {
        "file": str(path),
        "todo_count": len(items),
        "active_todo_count": sum(bool(item["active"]) for item in items),
        "commented_todo_count": sum(bool(item["commented"]) for item in items),
        "inactive_todo_count": sum(
            not bool(item["active"]) and not bool(item["commented"])
            for item in items
        ),
        "blocking_todo_count": sum(bool(item["blocking"]) for item in items),
        "items": items,
        "issues": [],
    }


def collect_todos(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        return {
            "file": str(path),
            "todo_count": 0,
            "active_todo_count": 0,
            "commented_todo_count": 0,
            "inactive_todo_count": 0,
            "blocking_todo_count": 0,
            "items": [],
            "issues": [{"type": "unreadable_file", "file": str(path), "message": str(exc)}],
        }
    return collect_todos_from_text(text, path)


def check_file(path: Path, source_backed: bool = False) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {"file": str(path), "ok": False, "issues": [{"type": "unreadable_file", "message": f"not valid UTF-8: {exc}"}]}
    except OSError as exc:
        return {"file": str(path), "ok": False, "issues": [{"type": "unreadable_file", "message": str(exc)}]}
    # Ignore inactive LaTeX comments while preserving newlines so issue line
    # numbers continue to map to the original file.
    body = prepare_active_tex(text)
    lines = body.splitlines()
    issues = []

    for line_no, line in enumerate(lines, start=1):
        if TODO_TOKEN_RE.search(line) and not VALID_TODO_RE.search(line):
            issues.append({"type": "todo_format", "line": line_no, "message": "TODO must use [TODO: ...]"})

    for match in CITE_RE.finditer(body):
        for key in [item.strip() for item in match.group(1).split(",")]:
            if SUSPICIOUS_KEY_RE.match(key):
                issues.append({"type": "suspicious_citation", "message": f"review citation key: {key}"})

    for index, line in enumerate(lines):
        if source_backed or HEADING_RE.search(line):
            continue
        if CLAIM_RE.search(line):
            window = line_window(lines, index)
            if not (EVIDENCE_RE.search(window) or CITE_RE.search(window)):
                issues.append({
                    "type": "unsupported_claim",
                    "line": index + 1,
                    "message": "strong claim has no nearby citation, ref, numeric evidence, or TODO",
                    "text": line.strip()[:160],
                })

    todo_status = collect_todos_from_text(text, path)
    return {
        "file": str(path),
        "ok": not issues,
        "issues": issues,
        "todo_count": todo_status["todo_count"],
        "active_todo_count": todo_status["active_todo_count"],
        "commented_todo_count": todo_status["commented_todo_count"],
        "inactive_todo_count": todo_status["inactive_todo_count"],
        "blocking_todo_count": todo_status["blocking_todo_count"],
        "todo_items": todo_status["items"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-backed",
        action="store_true",
        help="Skip unsupported-claim warnings when text is a faithful conversion from a supplied source document.",
    )
    parser.add_argument("tex_files", nargs="+")
    args = parser.parse_args()

    results = [check_file(Path(item), source_backed=args.source_backed) for item in args.tex_files]
    ok = all(result["ok"] for result in results)
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
