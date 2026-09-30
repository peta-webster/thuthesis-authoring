#!/usr/bin/env python3
"""Run lightweight LaTeX safety checks for generated thesis files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _shared_patterns import CITE_RE, SUSPICIOUS_KEY_RE, TODO_TOKEN_RE, VALID_TODO_RE, prepare_active_tex


ENV_TOKEN_RE = re.compile(r"\\(begin|end)\{([^}]+)\}")


def _scan_braces(text: str) -> tuple[int, list[dict[str, object]]]:
    balance = 0
    open_count = 0
    escaped = False
    issues: list[dict[str, object]] = []
    for line_no, line in enumerate(text.splitlines(keepends=True), start=1):
        for column, char in enumerate(line, start=1):
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == "{":
                balance += 1
                open_count += 1
            elif char == "}":
                balance -= 1
                if open_count:
                    open_count -= 1
                else:
                    issues.append({
                        "type": "unexpected_closing_brace",
                        "line": line_no,
                        "column": column,
                        "message": "closing brace has no preceding opening brace",
                    })
    return balance, issues


def brace_balance(text: str) -> int:
    """Return the net balance, retaining the original helper's API."""
    return _scan_braces(text)[0]


def check_file(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {"file": str(path), "ok": False, "issues": [{"type": "unreadable_file", "message": f"not valid UTF-8: {exc}"}]}
    except OSError as exc:
        return {"file": str(path), "ok": False, "issues": [{"type": "unreadable_file", "message": str(exc)}]}
    issues = []

    # Structural checks ignore commented-out LaTeX; a `% 见图 {A` note or a
    # commented `\begin{figure}` is not a real imbalance. Line count is
    # preserved, so reported line numbers still match the original file.
    body = prepare_active_tex(text)

    balance, brace_issues = _scan_braces(body)
    issues.extend(brace_issues)
    if balance != 0:
        issues.append({"type": "brace_balance", "message": f"brace balance is {balance}"})

    stack: list[tuple[str, int]] = []
    for line_no, line in enumerate(body.splitlines(), start=1):
        for match in ENV_TOKEN_RE.finditer(line):
            kind, env = match.groups()
            if kind == "begin":
                stack.append((env, line_no))
                continue
            if not stack:
                issues.append({"type": "environment", "line": line_no, "message": f"orphan end {env}"})
            else:
                last_env, last_line = stack.pop()
                if last_env != env:
                    issues.append({
                        "type": "environment",
                        "line": line_no,
                        "message": f"end {env} does not match begin {last_env} at line {last_line}",
                    })
    for env, line_no in stack:
        issues.append({"type": "environment", "line": line_no, "message": f"unclosed begin {env}"})

    for line_no, line in enumerate(body.splitlines(), start=1):
        if TODO_TOKEN_RE.search(line) and not VALID_TODO_RE.search(line):
            issues.append({"type": "todo_format", "line": line_no, "message": "use [TODO: ...] format"})

    for match in CITE_RE.finditer(body):
        keys = [key.strip() for key in match.group(1).split(",")]
        for key in keys:
            if SUSPICIOUS_KEY_RE.match(key):
                issues.append({"type": "suspicious_citation", "message": f"suspicious citation key: {key}"})

    return {"file": str(path), "ok": not issues, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tex_files", nargs="+")
    args = parser.parse_args()

    results = [check_file(Path(item)) for item in args.tex_files]
    ok = all(result["ok"] for result in results)
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
