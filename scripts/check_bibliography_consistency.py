#!/usr/bin/env python3
"""Check citation resolution and cited BibTeX entry renderability."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Optional

from _bibtex_parser import BibEntry, parse_bibtex
from _shared_patterns import CITE_RE, prepare_active_tex

# Retained as a compatibility export for callers that imported the old symbol.
# Parsing no longer depends on this expression because it cannot understand
# nested braces or quoted field values.
BIB_ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,", re.I)
NOCITE_RE = re.compile(r"\\nocite\s*\{([^}]*)\}")

NOTE_ONLY_FIELDS = frozenset({"note", "abstract", "annote"})
NON_DISPLAY_METADATA_FIELDS = frozenset({
    "file",
    "keywords",
    "keyword",
    "owner",
    "timestamp",
    "crossref",
})
RENDERABLE_FIELDS = frozenset({
    "author",
    "editor",
    "title",
    "journal",
    "booktitle",
    "publisher",
    "institution",
    "school",
    "organization",
    "howpublished",
    "year",
    "url",
    "doi",
    "eprint",
})


def resolve_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def default_tex_files(project_root: Path) -> list[Path]:
    data_dir = project_root / "data"
    if data_dir.exists():
        return sorted(data_dir.glob("*.tex"))
    return sorted(project_root.glob("*.tex"))


def default_bib_files(project_root: Path) -> list[Path]:
    ref_dir = project_root / "ref"
    if ref_dir.exists():
        return sorted(ref_dir.glob("*.bib"))
    return sorted(project_root.glob("*.bib"))


def collect_citations(tex_files: list[Path]) -> tuple[dict[str, list[dict[str, object]]], list[dict[str, object]]]:
    citations: dict[str, list[dict[str, object]]] = {}
    issues: list[dict[str, object]] = []
    for path in tex_files:
        if not path.exists():
            issues.append({"type": "missing_tex_file", "file": str(path)})
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            issues.append({"type": "unreadable_file", "file": str(path), "message": f"not valid UTF-8: {exc}"})
            continue
        except OSError as exc:
            issues.append({"type": "unreadable_file", "file": str(path), "message": str(exc)})
            continue
        text = prepare_active_tex(raw_text)
        for match in CITE_RE.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            for raw_key in match.group(1).split(","):
                key = raw_key.strip()
                if key:
                    citations.setdefault(key, []).append({"file": str(path), "line": line_no})
        for match in NOCITE_RE.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            for raw_key in match.group(1).split(","):
                key = raw_key.strip()
                if key:
                    citations.setdefault(key, []).append({"file": str(path), "line": line_no})
    return citations, issues


def collect_bib_entries(
    bib_files: list[Path],
) -> tuple[dict[str, list[BibEntry]], list[dict[str, object]]]:
    """Read BibTeX files and return entries indexed by citation key."""

    entries: dict[str, list[BibEntry]] = {}
    issues: list[dict[str, object]] = []
    for path in bib_files:
        if not path.exists():
            issues.append({"type": "missing_bib_file", "file": str(path)})
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            issues.append({"type": "unreadable_file", "file": str(path), "message": f"not valid UTF-8: {exc}"})
            continue
        except OSError as exc:
            issues.append({"type": "unreadable_file", "file": str(path), "message": str(exc)})
            continue
        parsed, parse_errors = parse_bibtex(raw_text, source=str(path))
        for error in parse_errors:
            issues.append({
                "type": "bib_parse_error",
                "file": str(path),
                **error,
            })
        for entry in parsed:
            entries.setdefault(entry.key, []).append(entry)
    for key, occurrences in sorted(entries.items()):
        if len(occurrences) > 1:
            issues.append({
                "type": "duplicate_bib_key",
                "key": key,
                "files": [entry.source for entry in occurrences],
                "locations": [
                    {"file": entry.source, "line": entry.line, "column": entry.column}
                    for entry in occurrences
                ],
            })
    return entries, issues


def collect_bib_keys(bib_files: list[Path]) -> tuple[dict[str, list[str]], list[dict[str, object]]]:
    """Compatibility wrapper returning key-to-file mappings."""

    entries, issues = collect_bib_entries(bib_files)
    keys = {
        key: [entry.source for entry in occurrences]
        for key, occurrences in entries.items()
    }
    return keys, issues


def _nonempty_fields(entry: BibEntry) -> dict[str, str]:
    return {
        name.lower(): value.strip()
        for name, value in entry.fields.items()
        if value.strip()
    }


def _check_cited_entry(
    entry: BibEntry,
    effective_fields: Optional[dict[str, str]] = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return fatal issues and advisory warnings for one cited entry."""

    fields = _nonempty_fields(entry) if effective_fields is None else effective_fields
    field_names = set(fields)
    location = {"file": entry.source, "line": entry.line, "column": entry.column}

    note_only = bool(field_names & NOTE_ONLY_FIELDS) and field_names.issubset(
        NOTE_ONLY_FIELDS | NON_DISPLAY_METADATA_FIELDS
    )
    if note_only:
        return ([{
            "type": "note_only_cited_entry",
            "key": entry.key,
            "entry_type": entry.entry_type,
            "fields": sorted(field_names),
            "location": location,
            "message": "cited entry stores its reference only in fields that the ThuThesis BST does not display",
        }], [])

    if not (field_names & RENDERABLE_FIELDS):
        return ([{
            "type": "non_renderable_cited_entry",
            "key": entry.key,
            "entry_type": entry.entry_type,
            "fields": sorted(field_names),
            "location": location,
            "message": "cited entry has no field that can produce visible bibliography content",
        }], [])

    missing_fields: list[str] = []
    if not ({"author", "editor", "organization"} & field_names):
        missing_fields.append("author")
    if "title" not in fields:
        missing_fields.append("title")
    if not ({"year", "date"} & field_names):
        missing_fields.append("year")
    warnings: list[dict[str, object]] = []
    if missing_fields:
        warnings.append({
            "type": "incomplete_bib_entry",
            "key": entry.key,
            "entry_type": entry.entry_type,
            "missing_fields": missing_fields,
            "location": location,
            "message": "entry remains renderable; do not invent missing bibliographic metadata",
        })
    return [], warnings


def _resolve_crossref_fields(
    key: str,
    bib_entries: dict[str, list[BibEntry]],
    stack: tuple[str, ...] = (),
) -> tuple[dict[str, str], list[dict[str, object]]]:
    """Resolve BibTeX crossref inheritance for one entry."""

    entry = bib_entries[key][0]
    own_fields = _nonempty_fields(entry)
    parent_key = own_fields.get("crossref", "").strip()
    if not parent_key:
        return own_fields, []

    location = {"file": entry.source, "line": entry.line, "column": entry.column}
    if parent_key not in bib_entries:
        return own_fields, [{
            "type": "missing_crossref_parent",
            "key": key,
            "parent_key": parent_key,
            "location": location,
            "message": "BibTeX crossref parent does not exist in the parsed bibliography files",
        }]

    if parent_key in stack or parent_key == key:
        cycle_start = stack.index(parent_key) if parent_key in stack else len(stack)
        cycle = list(stack[cycle_start:]) + [key, parent_key]
        return own_fields, [{
            "type": "crossref_cycle",
            "key": key,
            "parent_key": parent_key,
            "cycle": cycle,
            "location": location,
            "message": "BibTeX crossref chain contains a cycle",
        }]

    parent_fields, parent_issues = _resolve_crossref_fields(
        parent_key,
        bib_entries,
        stack + (key,),
    )
    effective_fields = dict(parent_fields)
    effective_fields.update(own_fields)
    return effective_fields, parent_issues


def check_project(project_root: Path, tex_files: list[Path], bib_files: list[Path]) -> dict[str, object]:
    citations, citation_issues = collect_citations(tex_files)
    bib_entries, bib_issues = collect_bib_entries(bib_files)
    bib_keys = set(bib_entries)
    issues = citation_issues + bib_issues
    warnings: list[dict[str, object]] = []

    if citations and not bib_files:
        issues.append({"type": "missing_bibliography", "message": "citations exist but no .bib files were found"})

    concrete_citations = {key: locations for key, locations in citations.items() if key != "*"}
    for key, locations in sorted(concrete_citations.items()):
        if key not in bib_keys:
            issues.append({"type": "missing_bib_entry", "key": key, "locations": locations})

    keys_to_check = set(concrete_citations) & bib_keys
    if "*" in citations:
        keys_to_check.update(bib_keys)

    seen_structural_issues: set[tuple[object, ...]] = set()
    for key in sorted(keys_to_check):
        effective_fields, crossref_issues = _resolve_crossref_fields(key, bib_entries)
        for crossref_issue in crossref_issues:
            signature = (
                crossref_issue.get("type"),
                crossref_issue.get("key"),
                crossref_issue.get("parent_key"),
                tuple(crossref_issue.get("cycle", [])),
            )
            if signature not in seen_structural_issues:
                issues.append(crossref_issue)
                seen_structural_issues.add(signature)
        entry_issues, entry_warnings = _check_cited_entry(
            bib_entries[key][0],
            effective_fields=effective_fields,
        )
        issues.extend(entry_issues)
        warnings.extend(entry_warnings)

    return {
        "project_root": str(project_root),
        "ok": not issues,
        "tex_files": [str(path) for path in tex_files],
        "bib_files": [str(path) for path in bib_files],
        "citation_count": sum(len(locations) for locations in citations.values()),
        "citation_keys": sorted(citations),
        "bib_key_count": len(bib_keys),
        "issues": issues,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root")
    parser.add_argument("tex_files", nargs="*", help="Optional .tex files relative to project root.")
    parser.add_argument("--bib-files", nargs="*", default=None, help="Optional .bib files relative to project root.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.exists() or not project_root.is_dir():
        reason = "project root does not exist" if not project_root.exists() else "project root is not a directory"
        print(json.dumps({
            "project_root": str(project_root),
            "ok": False,
            "issues": [{"type": "invalid_project_root", "message": reason}],
        }, ensure_ascii=False, indent=2))
        return 2
    tex_files = [resolve_path(project_root, item) for item in args.tex_files] if args.tex_files else default_tex_files(project_root)
    bib_files = [resolve_path(project_root, item) for item in args.bib_files] if args.bib_files is not None else default_bib_files(project_root)

    result = check_project(project_root, tex_files, bib_files)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
