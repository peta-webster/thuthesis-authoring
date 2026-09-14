#!/usr/bin/env python3
"""Atomic in-place text replacement for deterministic conversion scripts."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def validate_in_place_target(path: Path) -> None:
    if path.is_symlink():
        raise OSError(f"refusing to rewrite symbolic link: {path}")
    if not path.exists():
        raise OSError(f"input file does not exist: {path}")
    if not path.is_file():
        raise OSError(f"input path is not a regular file: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o222 == 0 or not os.access(path, os.W_OK):
        raise OSError(f"input file is not writable: {path}")


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Replace one regular file atomically while preserving its permission bits."""
    validate_in_place_target(path)
    original_mode = stat.S_IMODE(path.stat().st_mode)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, original_mode)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
