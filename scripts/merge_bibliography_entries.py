#!/usr/bin/env python3
"""Append validated BibTeX entries without rewriting existing bibliography content."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _atomic_write import atomic_write_text, validate_in_place_target
from _bibtex_parser import BibEntry, parse_bibtex, parse_bibtex_strict
from _thuthesis_paths import classify


def parse_unique_entries(
    text: str,
    source: str,
    *,
    strict_additions: bool = False,
) -> tuple[dict[str, BibEntry], list[dict[str, object]]]:
    if strict_additions:
        entries, errors = parse_bibtex_strict(text, source=source, reject_directives=True)
    else:
        entries, errors = parse_bibtex(text, source=source)
    issues: list[dict[str, object]] = [
        {"type": "bib_parse_error", "source": source, **error}
        for error in errors
    ]
    by_key: dict[str, BibEntry] = {}
    for entry in entries:
        if entry.key in by_key:
            issues.append({
                "type": "duplicate_bib_key",
                "source": source,
                "key": entry.key,
                "message": "the same citation key occurs more than once",
            })
        else:
            by_key[entry.key] = entry
    return by_key, issues


def merge_text(existing: str, additions: str, target: str = "<target>") -> tuple[str, dict[str, object]]:
    existing_entries, issues = parse_unique_entries(existing, target)
    new_entries, new_issues = parse_unique_entries(
        additions,
        "<additions>",
        strict_additions=True,
    )
    issues.extend(new_issues)
    if not new_entries and not new_issues:
        issues.append({"type": "no_bib_entries", "message": "no BibTeX entries were supplied"})
    collisions = sorted(set(existing_entries) & set(new_entries))
    for key in collisions:
        issues.append({
            "type": "existing_bib_key",
            "key": key,
            "message": "refusing to overwrite or duplicate an existing bibliography entry",
        })
    if issues:
        return existing, {
            "ok": False,
            "existing_key_count": len(existing_entries),
            "new_keys": sorted(new_entries),
            "issues": issues,
        }

    addition_text = additions.strip()
    if not existing:
        separator = ""
    elif existing.endswith("\n\n"):
        separator = ""
    elif existing.endswith("\n"):
        separator = "\n"
    else:
        separator = "\n\n"
    merged = existing + separator + addition_text + "\n"
    return merged, {
        "ok": True,
        "existing_key_count": len(existing_entries),
        "new_keys": sorted(new_entries),
        "added_count": len(new_entries),
        "existing_content_preserved_as_prefix": True,
        "issues": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and append new BibTeX entries without changing existing content."
    )
    parser.add_argument("project_root")
    parser.add_argument("target", help="Existing ref/*.bib file relative to the project root.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--entries-file", help="UTF-8 file containing only the entries to append.")
    source.add_argument("--text", help="BibTeX entries to append.")
    parser.add_argument("--in-place", action="store_true", help="Apply the merge; the default is a dry run.")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    classified = classify(root, args.target, allow_bibliography=True)
    if not classified["ok"]:
        print(json.dumps({"ok": False, "target_validation": classified}, ensure_ascii=False, indent=2))
        return 2
    target = root / str(classified["relative_path"])

    try:
        validate_in_place_target(target)
        existing = target.read_text(encoding="utf-8")
        if args.entries_file:
            additions = Path(args.entries_file).read_text(encoding="utf-8")
        else:
            additions = args.text
        merged, result = merge_text(existing, additions, target=str(target))
        result["target"] = str(target)
        result["changed"] = merged != existing
        result["applied"] = bool(args.in_place and result["ok"] and merged != existing)
        if result["applied"]:
            atomic_write_text(target, merged)
    except (OSError, UnicodeDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
