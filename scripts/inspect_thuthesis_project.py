#!/usr/bin/env python3
"""Inspect a ThuThesis-like project and emit a JSON summary."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _shared_patterns import prepare_active_tex
from _thuthesis_paths import is_protected, is_safe_target, is_sensitive_data_file

INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
MAX_TEX_FILES = 10_000
MAX_TEX_FILE_BYTES = 10 * 1024 * 1024


def normalize_tex_path(raw: str) -> str:
    value = raw.strip()
    if not value.endswith(".tex"):
        value = f"{value}.tex"
    return value


def scan_inputs(text: str) -> list[str]:
    return sorted({normalize_tex_path(match.group(1)) for match in INPUT_RE.finditer(text)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    warnings: list[str] = []
    if not root.exists():
        print(json.dumps({"error": f"project root does not exist: {root}"}, ensure_ascii=False, indent=2))
        return 2
    if not root.is_dir():
        print(json.dumps({"error": f"project root is not a directory: {root}"}, ensure_ascii=False, indent=2))
        return 2

    tex_files = sorted(root.rglob("*.tex"))
    if len(tex_files) > MAX_TEX_FILES:
        print(json.dumps({
            "error": f"project contains too many .tex files: {len(tex_files)} > {MAX_TEX_FILES}"
        }, ensure_ascii=False, indent=2))
        return 2
    main_files = []
    input_files: set[str] = set()
    documentclasses: dict[str, str] = {}

    for path in tex_files:
        try:
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                warnings.append(f"skip symbolic-link .tex file: {path}")
                continue
            if path.stat().st_size > MAX_TEX_FILE_BYTES:
                warnings.append(f"skip oversized .tex file (>10 MiB): {path}")
                continue
            text = prepare_active_tex(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            warnings.append(f"skip non-utf8 file: {path}")
            continue
        except OSError as exc:
            warnings.append(f"skip unreadable file: {path}: {exc}")
            continue
        class_match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", text)
        if class_match:
            documentclasses[rel] = class_match.group(1)
            if class_match.group(1) == "thuthesis":
                main_files.append(rel)
        if "\\begin{document}" in text:
            for item in scan_inputs(text):
                input_files.add(item)

    data_files = sorted(
        p.relative_to(root).as_posix()
        for p in (root / "data").glob("*.tex")
        if p.is_file() and not p.is_symlink()
    ) if (root / "data").exists() else []
    safe_targets = sorted({p for p in data_files + list(input_files) if is_safe_target(Path(p))})
    sensitive_data_files = sorted({p for p in data_files + list(input_files) if is_sensitive_data_file(Path(p))})
    protected_files = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and is_protected(p.relative_to(root))
    )
    official_release_signals = sorted(
        signal
        for signal in [
            "thuthesis.cls",
            "thuthesis.pdf",
            "thuthesis-example.pdf",
            "thuthesis-numeric.bst",
            "thu-fig-logo.pdf",
            "thu-text-logo.pdf",
            "ref/refs.bib",
        ]
        if (root / signal).exists()
    )

    result = {
        "project_root": str(root),
        "is_thuthesis_like": bool(main_files),
        "is_official_release_like": len(official_release_signals) >= 3,
        "official_release_signals": official_release_signals,
        "main_files": sorted(main_files),
        "documentclasses": documentclasses,
        "input_files": sorted(input_files),
        "data_files": data_files,
        "safe_targets": safe_targets,
        "sensitive_data_files": sensitive_data_files,
        "protected_files": protected_files,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
