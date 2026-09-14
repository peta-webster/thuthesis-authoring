#!/usr/bin/env python3
"""Compare edited LaTeX with a baseline and detect removed structural objects."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from _shared_patterns import CITE_RE, prepare_active_tex


HEADING_RE = re.compile(
    r"\\(chapter|section|subsection|subsubsection)\*?\{((?:[^{}]|\{[^{}]*\})*)\}"
)
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
REF_RE = re.compile(r"\\(?:ref|autoref|pageref|eqref)\*?\{([^}]+)\}")
CAPTION_RE = re.compile(r"\\caption(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}")
ENV_RE = re.compile(
    r"\\begin\{(figure|table|equation|align|gather|algorithm|lstlisting)\*?\}"
)


def collect_structure(text: str) -> dict[str, list[str]]:
    body = prepare_active_tex(text)
    citations = [
        key.strip()
        for match in CITE_RE.finditer(body)
        for key in match.group(1).split(",")
        if key.strip()
    ]
    return {
        "headings": [f"{match.group(1)}:{match.group(2).strip()}" for match in HEADING_RE.finditer(body)],
        "labels": [item.strip() for item in LABEL_RE.findall(body)],
        "references": [item.strip() for item in REF_RE.findall(body)],
        "citations": citations,
        "captions": [item.strip() for item in CAPTION_RE.findall(body)],
        "environments": [item for item in ENV_RE.findall(body)],
    }


def check_files(baseline: Path, current: Path) -> dict[str, object]:
    issues: list[dict[str, object]] = []
    try:
        baseline_text = baseline.read_text(encoding="utf-8")
        current_text = current.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {
            "baseline": str(baseline),
            "current": str(current),
            "ok": False,
            "issues": [{"type": "unreadable_file", "message": f"not valid UTF-8: {exc}"}],
        }
    except OSError as exc:
        return {
            "baseline": str(baseline),
            "current": str(current),
            "ok": False,
            "issues": [{"type": "unreadable_file", "message": str(exc)}],
        }

    before = collect_structure(baseline_text)
    after = collect_structure(current_text)
    for category, before_items in before.items():
        removed = Counter(before_items) - Counter(after[category])
        for item, count in sorted(removed.items()):
            issues.append({
                "type": f"removed_{category}",
                "item": item,
                "count": count,
                "message": f"existing {category} item was removed",
            })

    return {
        "baseline": str(baseline),
        "current": str(current),
        "ok": not issues,
        "before_counts": {key: len(value) for key, value in before.items()},
        "after_counts": {key: len(value) for key, value in after.items()},
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
