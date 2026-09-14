#!/usr/bin/env python3
"""Shared file-classification rules for ThuThesis-like projects.

These lists define this skill's safety boundary: which files may be edited by
default, which need explicit user confirmation, and which are template core
files that must never be touched. They previously lived as duplicate copies in
inspect_thuthesis_project.py and validate_tex_targets.py -- the two enforcement
points of that boundary -- where a change to one copy would silently make the
inspector and the validator disagree about the same file.
"""

from __future__ import annotations

import os
from pathlib import Path

PROTECTED_NAMES = {
    "thusetup.tex",
    "latexmkrc",
    "makefile",
    "build.lua",
    "thuthesis-example.tex",
    "thuthesis.pdf",
    "thuthesis-example.pdf",
    "thu-fig-logo.pdf",
    "thu-text-logo.pdf",
}
PROTECTED_SUFFIXES = {".cls", ".dtx", ".ins", ".bst", ".bbx", ".cbx"}
TEMPLATE_ASSET_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg"}
SENSITIVE_DATA_NAMES = {
    "comments.tex",
    "committee.tex",
    "resolution.tex",
    "resume.tex",
}


def is_protected(rel_path: Path) -> bool:
    """True for template core, build, style, logo, and figure asset files."""
    lower_name = rel_path.name.lower()
    if lower_name in PROTECTED_NAMES or rel_path.suffix.lower() in PROTECTED_SUFFIXES:
        return True
    return bool(rel_path.parts) and rel_path.parts[0] == "figures" and rel_path.suffix.lower() in TEMPLATE_ASSET_SUFFIXES


def is_data_tex(rel_path: Path) -> bool:
    parts = rel_path.parts
    return (
        len(parts) >= 2
        and parts[0] == "data"
        and ".." not in parts
        and rel_path.suffix == ".tex"
    )


def is_sensitive_data_file(rel_path: Path) -> bool:
    return is_data_tex(rel_path) and rel_path.name.lower() in SENSITIVE_DATA_NAMES


def is_safe_target(rel_path: Path) -> bool:
    return is_data_tex(rel_path) and not is_sensitive_data_file(rel_path)


def is_bibliography_target(rel_path: Path) -> bool:
    """True for bibliography databases directly under the conventional ref/ directory."""

    return len(rel_path.parts) == 2 and rel_path.parts[0] == "ref" and rel_path.suffix.lower() == ".bib"


def classify(
    root: Path,
    target: str,
    allow_sensitive_data: bool = False,
    allow_bibliography: bool = False,
) -> dict[str, object]:
    """Classify one intended edit target relative to a project root."""
    result: dict[str, object] = {"target": target, "ok": False, "reason": ""}
    if not root.exists():
        result["reason"] = "project root does not exist"
        return result
    if not root.is_dir():
        result["reason"] = "project root is not a directory"
        return result

    raw = Path(target)
    requested = raw if raw.is_absolute() else root / raw
    lexical = Path(os.path.abspath(requested))

    try:
        lexical_relative = lexical.relative_to(root)
    except ValueError:
        result["reason"] = "target is outside project root"
        return result

    cursor = root
    for part in lexical_relative.parts:
        cursor /= part
        if cursor.is_symlink():
            result["reason"] = "target path must not contain symbolic links"
            result["relative_path"] = lexical_relative.as_posix()
            return result

    resolved = lexical.resolve()

    try:
        rel = resolved.relative_to(root)
    except ValueError:
        result["reason"] = "target is outside project root"
        return result

    if is_protected(rel):
        result["reason"] = (
            "protected template asset"
            if rel.parts and rel.parts[0] == "figures"
            else "protected template or build file"
        )
    elif is_bibliography_target(rel):
        if allow_bibliography:
            result["ok"] = True
            result["reason"] = "safe ref/*.bib bibliography target"
        else:
            result["reason"] = "bibliography targets require --allow-bibliography"
    elif rel.suffix.lower() != ".tex":
        result["reason"] = "only .tex content files are valid default targets"
    elif not is_data_tex(rel):
        result["reason"] = "default editable files must be under data/"
    elif is_sensitive_data_file(rel) and not allow_sensitive_data:
        result["reason"] = "sensitive official data file; pass --allow-sensitive-data only after explicit user confirmation"
    else:
        result["ok"] = True
        result["reason"] = "safe data/*.tex target"

    result["relative_path"] = rel.as_posix()
    return result
