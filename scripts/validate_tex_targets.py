#!/usr/bin/env python3
"""Validate intended TeX and explicitly declared bibliography targets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _thuthesis_paths import classify


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-sensitive-data",
        action="store_true",
        help="Allow official data files such as committee/comments/resolution/resume after explicit user confirmation.",
    )
    parser.add_argument(
        "--allow-bibliography",
        action="store_true",
        help="Allow ref/*.bib targets when the workflow will append supplied references.",
    )
    parser.add_argument("project_root")
    parser.add_argument("targets", nargs="+")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    results = [
        classify(
            root,
            target,
            allow_sensitive_data=args.allow_sensitive_data,
            allow_bibliography=args.allow_bibliography,
        )
        for target in args.targets
    ]
    ok = all(item["ok"] for item in results)
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
