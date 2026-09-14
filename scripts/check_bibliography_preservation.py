#!/usr/bin/env python3
"""Verify that a bibliography edit was append-only and kept existing keys."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bibtex_parser import parse_bibtex, parse_bibtex_strict


def check_files(baseline: Path, current: Path) -> dict[str, object]:
    issues: list[dict[str, object]] = []
    for label, path in (("baseline", baseline), ("current", current)):
        if path.is_symlink():
            issues.append({"type": f"{label}_symlink", "file": str(path)})
        elif not path.exists() or not path.is_file():
            issues.append({"type": f"missing_{label}", "file": str(path)})
    if issues:
        return {"ok": False, "baseline": str(baseline), "current": str(current), "issues": issues}

    try:
        before = baseline.read_text(encoding="utf-8")
        after = current.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {
            "ok": False,
            "baseline": str(baseline),
            "current": str(current),
            "issues": [{"type": "unreadable_bibliography", "message": str(exc)}],
        }

    before_entries, before_errors = parse_bibtex(before, source=str(baseline))
    after_entries, after_errors = parse_bibtex(after, source=str(current))
    issues.extend({"type": "baseline_bib_parse_error", **error} for error in before_errors)
    issues.extend({"type": "current_bib_parse_error", **error} for error in after_errors)
    before_keys = [entry.key for entry in before_entries]
    after_keys = [entry.key for entry in after_entries]
    if not after.startswith(before):
        issues.append({
            "type": "existing_bibliography_content_changed",
            "message": "existing bibliography bytes must remain an exact prefix; append new entries instead",
        })
    missing_keys = sorted(set(before_keys) - set(after_keys))
    if missing_keys:
        issues.append({"type": "removed_bib_keys", "keys": missing_keys})

    suffix = after[len(before):] if after.startswith(before) else ""
    suffix_entries, suffix_errors = parse_bibtex_strict(
        suffix,
        source=f"{current}#appended-suffix",
        reject_directives=True,
    )
    issues.extend({"type": "invalid_appended_bibliography_content", **error} for error in suffix_errors)
    suffix_keys = [entry.key for entry in suffix_entries]
    duplicate_suffix_keys = sorted({key for key in suffix_keys if suffix_keys.count(key) > 1})
    if duplicate_suffix_keys:
        issues.append({"type": "duplicate_appended_bib_keys", "keys": duplicate_suffix_keys})
    reused_keys = sorted(set(before_keys) & set(suffix_keys))
    if reused_keys:
        issues.append({
            "type": "appended_existing_bib_keys",
            "keys": reused_keys,
            "message": "appended entries must use new citation keys",
        })

    return {
        "ok": not issues,
        "baseline": str(baseline),
        "current": str(current),
        "before_key_count": len(set(before_keys)),
        "after_key_count": len(set(after_keys)),
        "added_keys": sorted(set(suffix_keys) - set(before_keys)),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("current")
    args = parser.parse_args()

    result = check_files(Path(args.baseline), Path(args.current))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
