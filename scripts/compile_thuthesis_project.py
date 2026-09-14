#!/usr/bin/env python3
"""Optionally compile a ThuThesis project and report structured results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import check_bibliography_artifacts
from _subprocess_safety import run_captured


COMMON_TEX_DIRS = [
    Path("/Library/TeX/texbin"),
]

# A first XeLaTeX run on a CJK thesis builds font caches and runs BibTeX plus
# several passes, which routinely exceeds two minutes on a cold machine.
DEFAULT_TIMEOUT = 600


class CompileInputError(ValueError):
    """A user-facing compile request error."""


def bibliography_not_checked(reason: str) -> dict[str, object]:
    return {
        "ok": False,
        "skipped": True,
        "reason": reason,
        "issues": [],
        "warnings": [],
    }


def find_executable(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    for directory in COMMON_TEX_DIRS:
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def choose_main(root: Path, requested: Optional[str]) -> Optional[Path]:
    if requested:
        raw = Path(requested)
        if raw.name.startswith("-"):
            raise CompileInputError("main file name must not start with '-'")
        if raw.suffix.lower() != ".tex":
            raise CompileInputError("main file must have a .tex extension")
        candidate = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise CompileInputError("main file must stay inside the project root") from exc
        unresolved = raw if raw.is_absolute() else root / raw
        if unresolved.is_symlink():
            raise CompileInputError("main file must not be a symbolic link")
        if not candidate.is_file():
            raise CompileInputError(f"main file does not exist: {candidate}")
        return candidate
    candidates = []
    for path in root.glob("*.tex"):
        if path.is_symlink() or not path.is_file() or path.name.startswith("-"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "\\documentclass" in text and "thuthesis" in text and "\\begin{document}" in text:
            candidates.append(path)
    return sorted(candidates)[0] if candidates else None


def artifact_state(path: Path) -> Optional[dict[str, object]]:
    """Return a stable fingerprint, rejecting unsafe output aliases."""

    if path.is_symlink():
        raise CompileInputError(f"compile artifact must not be a symbolic link: {path}")
    if not path.exists():
        return None
    if not path.is_file():
        raise CompileInputError(f"compile artifact must be a regular file: {path}")
    stat_result = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "size": stat_result.st_size,
        "mtime_ns": stat_result.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def run_command(command: list[str], cwd: Path, timeout: int = DEFAULT_TIMEOUT) -> dict[str, object]:
    env = os.environ.copy()
    executable = Path(command[0])
    if executable.is_absolute():
        env["PATH"] = f"{executable.parent}{os.pathsep}{env.get('PATH', '')}"
    elif Path("/Library/TeX/texbin").exists():
        env["PATH"] = f"/Library/TeX/texbin{os.pathsep}{env.get('PATH', '')}"
    try:
        completed = run_captured(command, cwd=cwd, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") + "\n" + (exc.stderr or ""))[-12000:]
        return {
            "command": command,
            "returncode": None,
            "ok": False,
            "output_tail": output,
            "timed_out": True,
            "reason": f"command timed out after {exc.timeout}s",
        }
    except OSError as exc:
        return {
            "command": command,
            "returncode": None,
            "ok": False,
            "output_tail": "",
            "environment_limited": True,
            "reason": f"unable to start compile command: {exc}",
        }
    output = (completed.stdout + "\n" + completed.stderr)[-12000:]
    missing_tool = any(
        marker in output
        for marker in [
            "xetex: command not found",
            "xelatex: command not found",
            "latexmk: command not found",
            "pdflatex: command not found",
            "lualatex: command not found",
            "No such file or directory: 'xetex'",
            "No such file or directory: 'xelatex'",
            "No such file or directory: 'latexmk'",
            "fontspec)                The font",
            "cannot be found",
            "mktextfm",
        ]
    )
    result = {
        "command": command,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "output_tail": output,
    }
    if missing_tool and completed.returncode != 0:
        result["environment_limited"] = True
        result["reason"] = "TeX command required by the project is unavailable"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root")
    parser.add_argument("--main")
    parser.add_argument(
        "--allow-project-build-config",
        action="store_true",
        help=(
            "Allow project-controlled latexmkrc files or the Makefile fallback. "
            "Use only after the user explicitly confirms the project is trusted."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Seconds to allow the compile command to run (default: {DEFAULT_TIMEOUT}).",
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    if not root.exists() or not root.is_dir():
        reason = "project root does not exist" if not root.exists() else "project root is not a directory"
        print(json.dumps({
            "ok": False,
            "compile_ok": False,
            "bibliography_artifacts": bibliography_not_checked("compile was not started"),
            "reason": reason,
            "project_root": str(root),
        }, ensure_ascii=False, indent=2))
        return 2
    if args.timeout <= 0:
        print(json.dumps({
            "ok": False,
            "compile_ok": False,
            "bibliography_artifacts": bibliography_not_checked("compile was not started"),
            "reason": "timeout must be greater than zero",
        }, ensure_ascii=False, indent=2))
        return 2
    try:
        main_file = choose_main(root, args.main)
    except CompileInputError as exc:
        print(json.dumps({
            "ok": False,
            "compile_ok": False,
            "bibliography_artifacts": bibliography_not_checked("compile was not started"),
            "reason": str(exc),
        }, ensure_ascii=False, indent=2))
        return 2
    if main_file is None:
        print(json.dumps({
            "ok": False,
            "compile_ok": False,
            "bibliography_artifacts": bibliography_not_checked("compile was not started"),
            "reason": "no thuthesis main .tex file found",
        }, ensure_ascii=False, indent=2))
        return 1

    main_relative = main_file.relative_to(root)
    main_argument = f"./{main_relative.as_posix()}"
    artifact_paths = {
        suffix.lstrip("."): main_file.with_suffix(suffix)
        for suffix in (".pdf", ".aux", ".bbl", ".blg")
    }
    try:
        artifact_before = {name: artifact_state(path) for name, path in artifact_paths.items()}
    except CompileInputError as exc:
        print(json.dumps({
            "ok": False,
            "compile_ok": False,
            "bibliography_artifacts": bibliography_not_checked("compile was not started"),
            "reason": str(exc),
        }, ensure_ascii=False, indent=2))
        return 2

    latexmk = find_executable("latexmk")
    make = find_executable("make")
    if latexmk:
        command = [latexmk]
        if not args.allow_project_build_config:
            command.append("-norc")
        command.extend([
            "-g",
            "-xelatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            main_argument,
        ])
        result = run_command(
            command,
            root,
            timeout=args.timeout,
        )
    elif (root / "Makefile").exists() and make and args.allow_project_build_config:
        result = run_command([make, "thesis"], root, timeout=args.timeout)
    else:
        reason = "latexmk and usable make target are unavailable"
        if (root / "Makefile").exists() and make and not args.allow_project_build_config:
            reason = "latexmk is unavailable and the project Makefile is disabled until --allow-project-build-config is explicitly confirmed"
        print(json.dumps({
            "ok": False,
            "compile_ok": False,
            "bibliography_artifacts": bibliography_not_checked("compile was not started"),
            "environment_limited": True,
            "reason": reason,
            "main_file": main_relative.as_posix(),
        }, ensure_ascii=False, indent=2))
        return 2

    result["main_file"] = main_relative.as_posix()
    result["project_build_config_allowed"] = args.allow_project_build_config
    pdf_path = artifact_paths["pdf"]
    preliminary_bibliography_artifacts: Optional[dict[str, object]] = None
    if result.get("ok"):
        try:
            artifact_after = {name: artifact_state(path) for name, path in artifact_paths.items()}
        except CompileInputError as exc:
            result["ok"] = False
            result["reason"] = str(exc)
            artifact_after = {}
        freshness = {
            name: artifact_after.get(name) is not None and artifact_after.get(name) != artifact_before.get(name)
            for name in artifact_paths
        }
        result["artifact_freshness"] = freshness
        if result.get("ok") and artifact_after.get("pdf") is None:
            result["ok"] = False
            result["reason"] = "compile command returned success but the expected PDF was not created"
        elif result.get("ok") and not freshness["pdf"]:
            result["ok"] = False
            result["reason"] = "compile command returned success but the expected PDF was not refreshed"
        elif result.get("ok") and artifact_after.get("aux") is None:
            result["ok"] = False
            result["reason"] = "compile command returned success but the expected AUX file was not created"
        elif result.get("ok") and not freshness["aux"]:
            result["ok"] = False
            result["reason"] = "compile command returned success but the expected AUX file was not refreshed"
        elif result.get("ok"):
            preliminary_bibliography_artifacts = check_bibliography_artifacts.check_artifacts(
                root,
                main_file,
            )
            if preliminary_bibliography_artifacts.get("bibliography_requested"):
                stale_bibliography_artifacts = [
                    name
                    for name in ("bbl", "blg")
                    if artifact_after.get(name) is None or not freshness[name]
                ]
                if stale_bibliography_artifacts:
                    result["ok"] = False
                    result["reason"] = (
                        "compile command returned success but bibliography was requested and "
                        "the following artifacts were not refreshed: "
                        + ", ".join(stale_bibliography_artifacts)
                    )
            if result.get("ok"):
                result["pdf_path"] = str(pdf_path)
    compile_ok = bool(result.get("ok"))
    result["compile_ok"] = compile_ok
    if compile_ok:
        bibliography_artifacts = (
            preliminary_bibliography_artifacts
            if preliminary_bibliography_artifacts is not None
            else check_bibliography_artifacts.check_artifacts(root, main_file)
        )
    else:
        bibliography_artifacts = bibliography_not_checked("compile did not complete successfully")
    result["bibliography_artifacts"] = bibliography_artifacts
    result["ok"] = compile_ok and bool(bibliography_artifacts.get("ok"))
    if compile_ok and not bibliography_artifacts.get("ok"):
        result["reason"] = "compile succeeded but the bibliography artifact audit failed"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("environment_limited"):
        return 2
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
