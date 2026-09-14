#!/usr/bin/env python3
"""Run every pre-completion check for generated thesis files in one pass.

This is the single entry point behind references/quality-gates.md. Running the
individual checkers separately works, but it is easy to skip one; this wrapper
runs target validation, LaTeX safety, the TODO/claim audit, and bibliography
consistency together and reports one overall verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import check_bibliography_consistency
import check_bibliography_preservation
import check_latex_safety
import check_preservation
import check_todo_and_claims
from _thuthesis_paths import classify


MAIN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.tex$")
INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^{}]+)\}")
MAX_MAIN_GRAPH_FILES = 10_000
MAX_MAIN_GRAPH_FILE_BYTES = 10 * 1024 * 1024


def skipped_main_todo_status() -> dict[str, object]:
    return {
        "audit_skipped": True,
        "reason": "--main not provided",
        "main_file": None,
        "reachable_files": [],
        "todo_count": 0,
        "active_todo_count": 0,
        "commented_todo_count": 0,
        "inactive_todo_count": 0,
        "blocking_todo_count": 0,
        "items": [],
        "audit_complete": False,
        "issues": [],
    }


def _project_file_issue(root: Path, path: Path) -> dict[str, object] | None:
    lexical = Path(os.path.abspath(path))
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        return {"type": "input_outside_project", "file": str(path)}
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            return {"type": "input_symlink", "file": str(cursor)}
    if not lexical.exists():
        return {"type": "missing_input", "file": str(lexical)}
    if not lexical.is_file():
        return {"type": "input_not_file", "file": str(lexical)}
    try:
        if lexical.stat().st_size > MAX_MAIN_GRAPH_FILE_BYTES:
            return {"type": "oversized_input", "file": str(lexical)}
    except OSError as exc:
        return {"type": "unreadable_input", "file": str(lexical), "message": str(exc)}
    return None


def _resolve_literal_input(root: Path, current: Path, raw: str) -> tuple[Path | None, dict[str, object] | None]:
    value = raw.strip()
    if not value or "\\" in value or any(char in value for char in "{}%#~"):
        return None, {"type": "dynamic_or_unsupported_input", "source": str(current), "input": raw}
    requested = Path(value)
    if requested.is_absolute():
        return None, {"type": "input_outside_project", "source": str(current), "input": raw}
    if requested.suffix and requested.suffix.lower() != ".tex":
        return None, {"type": "non_tex_input", "source": str(current), "input": raw}
    if not requested.suffix:
        requested = requested.with_suffix(".tex")

    candidates: list[Path] = []
    seen: set[Path] = set()
    for base in (root, current.parent):
        candidate = Path(os.path.abspath(base / requested))
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.exists() or candidate.is_symlink():
            candidates.append(candidate)
    valid: list[Path] = []
    issues: list[dict[str, object]] = []
    for candidate in candidates:
        issue = _project_file_issue(root, candidate)
        if issue:
            issues.append(issue)
        else:
            valid.append(candidate)
    if len(valid) == 1:
        return valid[0], None
    if len(valid) > 1:
        return None, {
            "type": "ambiguous_input",
            "source": str(current),
            "input": raw,
            "candidates": [str(path) for path in valid],
        }
    if issues:
        issue = issues[0]
        issue.update({"source": str(current), "input": raw})
        return None, issue
    return None, {"type": "missing_input", "source": str(current), "input": raw}


def audit_main_todos(root: Path, raw_main: str | None) -> tuple[bool | None, dict[str, object]]:
    if raw_main is None:
        return None, skipped_main_todo_status()
    requested = Path(raw_main)
    if requested.is_absolute() or len(requested.parts) != 1 or not MAIN_NAME_RE.fullmatch(requested.name):
        status = skipped_main_todo_status()
        status.update({
            "audit_skipped": False,
            "reason": None,
            "main_file": raw_main,
            "issues": [{"type": "invalid_main", "message": "--main must be a root-level .tex filename"}],
        })
        return False, status
    main_path = root / requested
    initial_issue = _project_file_issue(root, main_path)
    if initial_issue:
        status = skipped_main_todo_status()
        status.update({
            "audit_skipped": False,
            "reason": None,
            "main_file": requested.as_posix(),
            "issues": [initial_issue],
        })
        return False, status

    visited: set[Path] = set()
    active_stack: list[Path] = []
    items: list[dict[str, object]] = []
    issues: list[dict[str, object]] = []

    def visit(path: Path) -> None:
        if len(visited) >= MAX_MAIN_GRAPH_FILES:
            issues.append({"type": "main_graph_too_large", "limit": MAX_MAIN_GRAPH_FILES})
            return
        if path in active_stack:
            start = active_stack.index(path)
            issues.append({
                "type": "input_cycle",
                "files": [str(item.relative_to(root)) for item in active_stack[start:] + [path]],
            })
            return
        if path in visited:
            return
        visited.add(path)
        active_stack.append(path)
        todo_result = check_todo_and_claims.collect_todos(path)
        items.extend(todo_result["items"])
        issues.extend(todo_result["issues"])
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            issues.append({"type": "unreadable_input", "file": str(path), "message": str(exc)})
            active_stack.pop()
            return
        from _shared_patterns import prepare_active_tex

        active_text = prepare_active_tex(text)
        for match in INPUT_RE.finditer(active_text):
            child, issue = _resolve_literal_input(root, path, match.group(1))
            if issue:
                issues.append(issue)
            elif child is not None:
                visit(child)
        active_stack.pop()

    visit(main_path)
    items.sort(key=lambda item: (str(item["file"]), int(item["line"])))
    audit_complete = not issues
    status = {
        "audit_skipped": False,
        "reason": None,
        "main_file": requested.as_posix(),
        "reachable_files": sorted(path.relative_to(root).as_posix() for path in visited),
        "todo_count": len(items),
        "active_todo_count": sum(bool(item["active"]) for item in items),
        "commented_todo_count": sum(bool(item["commented"]) for item in items),
        "inactive_todo_count": sum(
            not bool(item["active"]) and not bool(item["commented"])
            for item in items
        ),
        "blocking_todo_count": sum(bool(item["blocking"]) for item in items),
        "items": items,
        "audit_complete": audit_complete,
        "issues": issues,
    }
    return audit_complete and not items, status


def bibliography_inventory(root: Path, label: str) -> tuple[dict[str, bytes], list[dict[str, object]]]:
    """Read direct ``ref/*.bib`` files without following aliases."""

    inventory: dict[str, bytes] = {}
    issues: list[dict[str, object]] = []
    ref_dir = root / "ref"
    if ref_dir.is_symlink():
        return inventory, [{
            "type": f"{label}_bibliography_directory_symlink",
            "file": str(ref_dir),
        }]
    if not ref_dir.exists():
        return inventory, issues
    if not ref_dir.is_dir():
        return inventory, [{
            "type": f"{label}_bibliography_path_not_directory",
            "file": str(ref_dir),
        }]
    try:
        entries = ref_dir.iterdir()
        for path in entries:
            if path.suffix.lower() != ".bib":
                continue
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                issues.append({"type": f"{label}_bibliography_symlink", "file": str(path)})
            elif not path.is_file():
                issues.append({"type": f"{label}_bibliography_not_file", "file": str(path)})
            else:
                inventory[relative] = path.read_bytes()
    except OSError as exc:
        issues.append({
            "type": f"{label}_bibliography_inventory_error",
            "message": str(exc),
        })
    return inventory, issues


def audit_declared_bibliography_changes(
    baseline_root: Path,
    current_root: Path,
    declared_paths: set[str],
) -> dict[str, object]:
    """Reject bibliography mutations omitted from ``--bibliography-targets``."""

    before, before_issues = bibliography_inventory(baseline_root, "baseline")
    after, after_issues = bibliography_inventory(current_root, "current")
    changed = sorted(
        relative
        for relative in set(before) | set(after)
        if before.get(relative) != after.get(relative)
    )
    undeclared = sorted(set(changed) - declared_paths)
    issues = before_issues + after_issues
    if undeclared:
        issues.append({
            "type": "undeclared_bibliography_changes",
            "paths": undeclared,
            "message": "every changed ref/*.bib file must be declared with --bibliography-targets",
        })
    return {
        "ok": not issues,
        "changed_paths": changed,
        "declared_paths": sorted(declared_paths),
        "undeclared_paths": undeclared,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root")
    parser.add_argument("targets", nargs="+", help="Edited .tex files, relative to project root or absolute.")
    parser.add_argument(
        "--main",
        help="Explicit root-level user main whose project-local input graph should be audited for TODOs.",
    )
    parser.add_argument(
        "--source-backed",
        action="store_true",
        help="Skip unsupported-claim warnings for faithful conversion of a supplied source document.",
    )
    parser.add_argument(
        "--allow-sensitive-data",
        action="store_true",
        help="Permit official process files (committee/comments/resolution/resume) after explicit user confirmation.",
    )
    parser.add_argument(
        "--skip-bibliography",
        action="store_true",
        help="Skip the citation/bibliography gate when no citations or .bib files were touched.",
    )
    parser.add_argument(
        "--bibliography-targets",
        nargs="*",
        default=[],
        help="Edited ref/*.bib files that need target validation and append-only preservation checks.",
    )
    parser.add_argument(
        "--allow-existing-bibliography-changes",
        action="store_true",
        help="Skip append-only bibliography preservation after a user explicitly requests existing-entry changes.",
    )
    parser.add_argument(
        "--bibliography-change-reason",
        help="Required explanation when existing bibliography content may change.",
    )
    parser.add_argument(
        "--baseline-root",
        help=(
            "Directory containing pre-edit copies at the same relative target paths, "
            "including an inventory of every existing ref/*.bib file."
        ),
    )
    parser.add_argument(
        "--skip-preservation",
        action="store_true",
        help=(
            "Skip TeX structural preservation only for entirely new targets or a "
            "user-confirmed removal; bibliography preservation remains active."
        ),
    )
    parser.add_argument(
        "--preservation-skip-reason",
        help="Required explanation when --skip-preservation is used.",
    )
    args = parser.parse_args()

    if args.skip_preservation and not args.preservation_skip_reason:
        parser.error("--preservation-skip-reason is required with --skip-preservation")
    if args.skip_preservation and not args.baseline_root:
        parser.error("--baseline-root is required even when --skip-preservation is used")
    if args.preservation_skip_reason and not args.skip_preservation:
        parser.error("--preservation-skip-reason requires --skip-preservation")
    if args.skip_bibliography and args.bibliography_targets:
        parser.error("--skip-bibliography cannot be combined with --bibliography-targets")
    if args.allow_existing_bibliography_changes and not args.bibliography_change_reason:
        parser.error("--bibliography-change-reason is required with --allow-existing-bibliography-changes")
    if args.bibliography_change_reason and not args.allow_existing_bibliography_changes:
        parser.error("--bibliography-change-reason requires --allow-existing-bibliography-changes")
    if args.allow_existing_bibliography_changes and not args.bibliography_targets:
        parser.error("--allow-existing-bibliography-changes requires --bibliography-targets")

    root = Path(args.project_root).resolve()
    paths = [p if (p := Path(t)).is_absolute() else root / t for t in args.targets]
    bibliography_paths = [
        p if (p := Path(t)).is_absolute() else root / t
        for t in args.bibliography_targets
    ]

    gates: dict[str, object] = {}

    target_results = [classify(root, t, allow_sensitive_data=args.allow_sensitive_data) for t in args.targets]
    bibliography_target_results = [
        classify(root, target, allow_bibliography=True)
        for target in args.bibliography_targets
    ]
    declared_bibliography_paths = {
        str(item["relative_path"])
        for item in bibliography_target_results
        if item.get("ok") and item.get("relative_path")
    }
    gates["target_validation"] = {
        "ok": all(item["ok"] for item in target_results + bibliography_target_results),
        "results": target_results + bibliography_target_results,
        "tex_results": target_results,
        "bibliography_results": bibliography_target_results,
    }

    # Target validation is the read boundary, not merely one advisory gate.
    # Do not pass rejected absolute paths, traversal paths, or symlink aliases
    # to any checker: those checkers report matched source text and could leak
    # content from outside the project even though the final exit code is 1.
    if not gates["target_validation"]["ok"]:
        skipped = {
            "ok": False,
            "skipped": True,
            "reason": "target validation failed; no target content was read",
        }
        for name in (
            "latex_safety",
            "todo_and_claims",
            "preservation",
            "bibliography_preservation",
            "bibliography",
        ):
            gates[name] = dict(skipped)
        main_todo_status = skipped_main_todo_status()
        main_todo_status["reason"] = "target validation failed; main graph was not read"
        print(
            json.dumps(
                {
                    "ok": False,
                    "project_root": str(root),
                    "targets": [str(p) for p in paths],
                    "bibliography_targets": [str(p) for p in bibliography_paths],
                    "failed_gates": sorted(gates),
                    "gates": gates,
                    "submission_ready": None,
                    "main_todo_status": main_todo_status,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    safety_results = [check_latex_safety.check_file(path) for path in paths]
    gates["latex_safety"] = {
        "ok": all(item["ok"] for item in safety_results),
        "results": safety_results,
    }

    claim_results = [
        check_todo_and_claims.check_file(path, source_backed=args.source_backed) for path in paths
    ]
    gates["todo_and_claims"] = {
        "ok": all(item["ok"] for item in claim_results),
        "source_backed": args.source_backed,
        "results": claim_results,
    }

    if args.skip_preservation:
        gates["preservation"] = {
            "ok": True,
            "skipped": True,
            "reason": args.preservation_skip_reason,
        }
    elif args.baseline_root:
        baseline_root = Path(args.baseline_root).resolve()
        preservation_results = []
        if not baseline_root.exists() or not baseline_root.is_dir():
            gates["preservation"] = {
                "ok": False,
                "results": [],
                "issues": [{
                    "type": "invalid_baseline_root",
                    "message": "baseline root does not exist or is not a directory",
                }],
            }
        else:
            for target, current, classified in zip(args.targets, paths, target_results):
                relative = classified.get("relative_path")
                if not relative:
                    preservation_results.append({
                        "baseline": None,
                        "current": str(current),
                        "ok": False,
                        "issues": [{
                            "type": "invalid_target",
                            "message": f"cannot map invalid target to baseline: {target}",
                        }],
                    })
                    continue
                preservation_results.append(
                    check_preservation.check_files(baseline_root / str(relative), current)
                )
            gates["preservation"] = {
                "ok": all(item["ok"] for item in preservation_results),
                "baseline_root": str(baseline_root),
                "results": preservation_results,
            }
    else:
        gates["preservation"] = {
            "ok": False,
            "results": [],
            "issues": [{
                "type": "baseline_required",
                "message": (
                    "provide --baseline-root with pre-edit copies; for entirely new TeX targets, "
                    "also use --skip-preservation with an explicit reason"
                ),
            }],
        }

    bibliography_baseline_root = Path(args.baseline_root).resolve() if args.baseline_root else None
    valid_bibliography_baseline = bool(
        bibliography_baseline_root
        and bibliography_baseline_root.exists()
        and bibliography_baseline_root.is_dir()
    )
    bibliography_change_audit = (
        audit_declared_bibliography_changes(
            bibliography_baseline_root,
            root,
            declared_bibliography_paths,
        )
        if valid_bibliography_baseline and bibliography_baseline_root is not None
        else None
    )

    if args.bibliography_targets and not valid_bibliography_baseline:
        gates["bibliography_preservation"] = {
            "ok": False,
            "results": [],
            "issues": [{
                "type": "baseline_required",
                "message": "bibliography targets require --baseline-root even when TeX preservation is skipped",
            }],
        }
    elif not args.bibliography_targets:
        audit_ok = bibliography_change_audit is None or bool(bibliography_change_audit["ok"])
        gates["bibliography_preservation"] = {
            "ok": audit_ok,
            "skipped": audit_ok,
            "reason": "no bibliography changes detected" if audit_ok else "undeclared bibliography changes detected",
            "change_declaration_audit": bibliography_change_audit,
        }
    elif args.allow_existing_bibliography_changes:
        gates["bibliography_preservation"] = {
            "ok": bool(bibliography_change_audit and bibliography_change_audit["ok"]),
            "skipped": True,
            "reason": args.bibliography_change_reason,
            "change_declaration_audit": bibliography_change_audit,
        }
    else:
        assert bibliography_baseline_root is not None
        bibliography_preservation_results = []
        for target, current, classified in zip(
            args.bibliography_targets,
            bibliography_paths,
            bibliography_target_results,
        ):
            relative = classified.get("relative_path")
            if not relative:
                bibliography_preservation_results.append({
                    "baseline": None,
                    "current": str(current),
                    "ok": False,
                    "issues": [{
                        "type": "invalid_target",
                        "message": f"cannot map invalid bibliography target to baseline: {target}",
                    }],
                })
                continue
            bibliography_preservation_results.append(
                check_bibliography_preservation.check_files(
                    bibliography_baseline_root / str(relative),
                    current,
                )
            )
        gates["bibliography_preservation"] = {
            "ok": (
                bool(bibliography_change_audit and bibliography_change_audit["ok"])
                and all(item["ok"] for item in bibliography_preservation_results)
            ),
            "baseline_root": str(bibliography_baseline_root),
            "change_declaration_audit": bibliography_change_audit,
            "results": bibliography_preservation_results,
        }

    if args.skip_bibliography:
        gates["bibliography"] = {"ok": True, "skipped": True}
    else:
        bib_result = check_bibliography_consistency.check_project(
            root,
            [p for p in paths if p.suffix == ".tex"],
            check_bibliography_consistency.default_bib_files(root),
        )
        gates["bibliography"] = bib_result

    ok = all(bool(gate["ok"]) for gate in gates.values())
    failed = sorted(name for name, gate in gates.items() if not gate["ok"])
    submission_ready, main_todo_status = audit_main_todos(root, args.main)

    print(
        json.dumps(
            {
                "ok": ok,
                "project_root": str(root),
                "targets": [str(p) for p in paths],
                "bibliography_targets": [str(p) for p in bibliography_paths],
                "failed_gates": failed,
                "gates": gates,
                "submission_ready": submission_ready,
                "main_todo_status": main_todo_status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
