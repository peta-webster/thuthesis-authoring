#!/usr/bin/env python3
"""Audit BibTeX artifacts produced by a ThuThesis compilation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, Optional


AUX_CITATION_RE = re.compile(r"\\citation\{([^{}]*)\}")
BIBITEM_COMMAND_RE = re.compile(r"\\bibitem\b")
BLG_FATAL_RE = re.compile(
    r"(?:error message|i couldn't (?:open|find)|i was expecting|repeated entry|illegal,|bad cross reference)",
    re.I,
)
BLG_WARNING_RE = re.compile(r"warning--", re.I)


def _read_utf8(path: Path, artifact_type: str) -> tuple[Optional[str], list[dict[str, object]]]:
    try:
        return path.read_text(encoding="utf-8"), []
    except UnicodeDecodeError as exc:
        return None, [{
            "type": f"unreadable_{artifact_type}",
            "file": str(path),
            "message": f"not valid UTF-8: {exc}",
        }]
    except OSError as exc:
        return None, [{
            "type": f"unreadable_{artifact_type}",
            "file": str(path),
            "message": str(exc),
        }]


def collect_aux_citations(aux_text: str) -> tuple[list[str], bool]:
    """Return unique citation keys and whether ``\\citation{*}`` was used."""

    keys: set[str] = set()
    wildcard = False
    for match in AUX_CITATION_RE.finditer(aux_text):
        for raw_key in match.group(1).split(","):
            key = raw_key.strip()
            if key == "*":
                wildcard = True
            elif key:
                keys.add(key)
    return sorted(keys), wildcard


def _body_payload(body: str) -> str:
    without_comments = re.sub(r"(?m)(?<!\\)%.*$", "", body)
    without_scaffolding = re.sub(
        r"\\(?:newblock|allowbreak|relax|protect|ignorespaces)\b",
        "",
        without_comments,
    )
    return without_scaffolding.strip()


def _is_empty_bibitem(body: str) -> bool:
    payload = _body_payload(body)
    payload = re.sub(r"[\s{}\[\]().,;:~]+", "", payload)
    return not payload


def _is_only_z_marker(body: str) -> bool:
    payload = _body_payload(body)
    compact = re.sub(r"[\s{}().,;:~]+", "", payload)
    return compact.upper() == "[Z]"


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _scan_bibitem_headers(
    bbl_text: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Scan ``\\bibitem`` headers without flattening their optional labels."""

    headers: list[dict[str, object]] = []
    issues: list[dict[str, object]] = []
    length = len(bbl_text)
    for command in BIBITEM_COMMAND_RE.finditer(bbl_text):
        cursor = command.end()
        while cursor < length and bbl_text[cursor].isspace():
            cursor += 1

        if cursor < length and bbl_text[cursor] == "[":
            label_start = cursor
            square_depth = 1
            brace_depth = 0
            cursor += 1
            while cursor < length and square_depth:
                char = bbl_text[cursor]
                escaped = _is_escaped(bbl_text, cursor)
                if not escaped and char == "{":
                    brace_depth += 1
                elif not escaped and char == "}" and brace_depth:
                    brace_depth -= 1
                elif not escaped and brace_depth == 0 and char == "[":
                    square_depth += 1
                elif not escaped and brace_depth == 0 and char == "]":
                    square_depth -= 1
                cursor += 1
            if square_depth:
                issues.append({
                    "type": "malformed_bibitem_header",
                    "line": bbl_text.count("\n", 0, command.start()) + 1,
                    "message": "unterminated optional label in \\bibitem",
                })
                continue
            if brace_depth:
                issues.append({
                    "type": "malformed_bibitem_header",
                    "line": bbl_text.count("\n", 0, label_start) + 1,
                    "message": "unbalanced brace group in \\bibitem optional label",
                })
                continue
            while cursor < length and bbl_text[cursor].isspace():
                cursor += 1

        if cursor >= length or bbl_text[cursor] != "{":
            issues.append({
                "type": "malformed_bibitem_header",
                "line": bbl_text.count("\n", 0, command.start()) + 1,
                "message": "\\bibitem is missing its braced citation key",
            })
            continue

        key_start = cursor + 1
        depth = 1
        cursor += 1
        while cursor < length and depth:
            char = bbl_text[cursor]
            if not _is_escaped(bbl_text, cursor):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        key_end = cursor
                        cursor += 1
                        break
            cursor += 1
        if depth:
            issues.append({
                "type": "malformed_bibitem_header",
                "line": bbl_text.count("\n", 0, command.start()) + 1,
                "message": "unterminated citation key in \\bibitem",
            })
            continue

        key = bbl_text[key_start:key_end].strip()
        if not key:
            issues.append({
                "type": "malformed_bibitem_header",
                "line": bbl_text.count("\n", 0, command.start()) + 1,
                "message": "\\bibitem has an empty citation key",
            })
            continue
        headers.append({
            "key": key,
            "start": command.start(),
            "end": cursor,
            "line": bbl_text.count("\n", 0, command.start()) + 1,
        })
    return headers, issues


def parse_bbl_items(bbl_text: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return BibTeX items with bodies and structural issues."""

    headers, issues = _scan_bibitem_headers(bbl_text)
    items: list[dict[str, object]] = []
    for index, header in enumerate(headers):
        body_end = int(headers[index + 1]["start"]) if index + 1 < len(headers) else len(bbl_text)
        body = bbl_text[int(header["end"]):body_end]
        if index + 1 == len(headers):
            end_marker = body.find(r"\end{thebibliography}")
            if end_marker >= 0:
                body = body[:end_marker]
        items.append({"key": header["key"], "line": header["line"], "body": body})

    seen: dict[str, list[int]] = {}
    for item in items:
        key = str(item["key"])
        seen.setdefault(key, []).append(int(item["line"]))
        body = str(item["body"])
        if _is_empty_bibitem(body):
            issues.append({
                "type": "empty_bibitem",
                "key": key,
                "line": item["line"],
                "message": "compiled bibliography item has no visible content",
            })
        elif _is_only_z_marker(body):
            issues.append({
                "type": "z_only_bibitem",
                "key": key,
                "line": item["line"],
                "message": "compiled bibliography item contains only the fallback '[Z]' marker",
            })
    for key, lines in sorted(seen.items()):
        if len(lines) > 1:
            issues.append({"type": "duplicate_bbl_key", "key": key, "lines": lines})
    return items, issues


def check_artifacts(
    project_root: Path,
    main_file: Path,
    citation_keys: Optional[Iterable[str]] = None,
) -> dict[str, object]:
    """Check ``.aux``, ``.bbl``, and ``.blg`` files for one compiled main file."""

    root = project_root.resolve()
    main = main_file.resolve()
    aux_path = main.with_suffix(".aux")
    bbl_path = main.with_suffix(".bbl")
    blg_path = main.with_suffix(".blg")
    issues: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    aux_text: Optional[str] = None
    wildcard = False
    if citation_keys is None:
        if not aux_path.is_file():
            issues.append({
                "type": "missing_aux_file",
                "file": str(aux_path),
                "message": "cannot verify compiled citation coverage without the main .aux file",
            })
            expected_keys: list[str] = []
        else:
            aux_text, read_issues = _read_utf8(aux_path, "aux")
            issues.extend(read_issues)
            expected_keys, wildcard = collect_aux_citations(aux_text or "")
    else:
        supplied_keys = [key.strip() for key in citation_keys]
        expected_keys = sorted({key for key in supplied_keys if key and key != "*"})
        wildcard = "*" in supplied_keys
        if aux_path.is_file():
            aux_text, read_issues = _read_utf8(aux_path, "aux")
            issues.extend(read_issues)

    # A ThuThesis main may keep \bibliography{...} even before the draft has
    # any citations.  BibTeX then emits a .blg error despite a successful PDF
    # build.  Audit bibliography artifacts only when the AUX actually requests
    # concrete citations or \nocite{*}; \bibdata alone is not a rendered
    # bibliography request.
    bibliography_requested = bool(expected_keys or wildcard)

    stale_bbl = bbl_path.is_file() and not bibliography_requested
    stale_blg = blg_path.is_file() and not bibliography_requested
    for artifact_type, path, stale in (
        ("bbl", bbl_path, stale_bbl),
        ("blg", blg_path, stale_blg),
    ):
        if stale:
            warnings.append({
                "type": "stale_bibliography_artifact",
                "artifact": artifact_type,
                "file": str(path),
                "message": "current .aux requests no bibliography; this leftover artifact was not audited",
            })

    bbl_text: Optional[str] = None
    items: list[dict[str, object]] = []
    if bibliography_requested and bbl_path.is_file():
        bbl_text, read_issues = _read_utf8(bbl_path, "bbl")
        issues.extend(read_issues)
        if bbl_text is not None:
            if bibliography_requested and not bbl_text.strip():
                issues.append({"type": "empty_bbl_file", "file": str(bbl_path)})
            if bbl_text.strip() and r"\begin{thebibliography}" not in bbl_text:
                issues.append({
                    "type": "malformed_bbl_file",
                    "file": str(bbl_path),
                    "message": "compiled .bbl has no thebibliography environment",
                })
            items, item_issues = parse_bbl_items(bbl_text)
            for issue in item_issues:
                issues.append({**issue, "file": str(bbl_path)})
    elif bibliography_requested:
        issues.append({"type": "missing_bbl_file", "file": str(bbl_path)})

    actual_keys = sorted({str(item["key"]) for item in items})
    if bibliography_requested and not wildcard:
        for key in sorted(set(expected_keys) - set(actual_keys)):
            issues.append({
                "type": "missing_bbl_entry",
                "key": key,
                "file": str(bbl_path),
                "message": "cited key is absent from the compiled bibliography",
            })
        for key in sorted(set(actual_keys) - set(expected_keys)):
            warnings.append({
                "type": "uncited_bbl_entry",
                "key": key,
                "file": str(bbl_path),
            })

    blg_text: Optional[str] = None
    blg_warning_lines: list[str] = []
    if bibliography_requested and blg_path.is_file():
        blg_text, read_issues = _read_utf8(blg_path, "blg")
        issues.extend(read_issues)
        if blg_text is not None:
            if bibliography_requested and not blg_text.strip():
                issues.append({"type": "empty_blg_file", "file": str(blg_path)})
            for line_number, line in enumerate(blg_text.splitlines(), start=1):
                if BLG_FATAL_RE.search(line):
                    issues.append({
                        "type": "bibtex_log_error",
                        "file": str(blg_path),
                        "line": line_number,
                        "message": line.strip(),
                    })
                elif BLG_WARNING_RE.search(line):
                    blg_warning_lines.append(line.strip())
                    warnings.append({
                        "type": "bibtex_log_warning",
                        "file": str(blg_path),
                        "line": line_number,
                        "message": line.strip(),
                    })
    elif bibliography_requested:
        issues.append({"type": "missing_blg_file", "file": str(blg_path)})

    return {
        "ok": not issues,
        "project_root": str(root),
        "main_file": str(main),
        "citation_keys": expected_keys,
        "citation_wildcard": wildcard,
        "bibliography_requested": bibliography_requested,
        "aux": {"path": str(aux_path), "exists": aux_path.is_file()},
        "bbl": {
            "path": str(bbl_path),
            "exists": bbl_path.is_file(),
            "stale": stale_bbl,
            "audit_skipped": not bibliography_requested,
            "bibitem_count": len(items),
            "keys": actual_keys,
        },
        "blg": {
            "path": str(blg_path),
            "exists": blg_path.is_file(),
            "stale": stale_blg,
            "audit_skipped": not bibliography_requested,
            "warning_count": len(blg_warning_lines),
        },
        "issues": issues,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root")
    parser.add_argument("--main", required=True, help="Main .tex file, relative to the project root or absolute.")
    parser.add_argument(
        "--citation-key",
        action="append",
        default=None,
        help="Expected citation key; repeat as needed. Defaults to citations in the main .aux file.",
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    if not root.exists() or not root.is_dir():
        print(json.dumps({
            "ok": False,
            "project_root": str(root),
            "issues": [{"type": "invalid_project_root"}],
        }, ensure_ascii=False, indent=2))
        return 2
    raw_main = Path(args.main)
    main_file = raw_main.resolve() if raw_main.is_absolute() else (root / raw_main).resolve()
    try:
        main_file.relative_to(root)
    except ValueError:
        print(json.dumps({
            "ok": False,
            "project_root": str(root),
            "issues": [{"type": "main_outside_project", "file": str(main_file)}],
        }, ensure_ascii=False, indent=2))
        return 2

    result = check_artifacts(root, main_file, citation_keys=args.citation_key)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
