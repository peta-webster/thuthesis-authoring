#!/usr/bin/env python3
"""Replay the reviewed teaching fixture locally; this does not invoke an Agent."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "minimal"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compile_thuthesis_project as compiler
import init_thuthesis_project as initializer

TARGETS = ["data/abstract.tex", "data/chap01.tex", "data/chap02.tex", "data/chap03.tex"]
TODOS = ["[TODO: 核对所在院系的最新提交要求。]", "[TODO: 确认导师对章节安排的具体要求。]"]
LOG_ERRORS = re.compile(
    r"Missing character:|(?:Citation|Reference) .+ undefined|"
    r"There were undefined (?:references|citations)|Overfull \\[hv]box",
    re.IGNORECASE,
)


class ExampleError(RuntimeError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def input_hashes(example: Path = EXAMPLE) -> dict[str, str]:
    paths = [example / name for name in ("source.md", "data.json", "template.json")]
    paths += sorted((example / "references").glob("*"))
    paths += sorted((example / "expected").rglob("*.tex"))
    return {p.relative_to(example).as_posix(): digest(p) for p in paths if p.is_file()}


def validate_materials(example: Path = EXAMPLE) -> dict[str, object]:
    data = json.loads((example / "data.json").read_text(encoding="utf-8"))
    values = data["values"]
    if values != [2, 4, 6]:
        raise ExampleError("Teaching values must remain [2, 4, 6] for this reviewed fixture")
    calculated = {"count": len(values), "sum": sum(values), "mean": sum(values) / len(values)}
    if any(calculated[k] != data["expected_" + k] for k in calculated):
        raise ExampleError("Teaching calculations do not match data.json")
    source = (example / "source.md").read_text(encoding="utf-8")
    body = "\n".join((example / "expected" / p).read_text(encoding="utf-8") for p in TARGETS)
    for todo in TODOS:
        if source.count(todo) != 1 or body.count(todo) != 1:
            raise ExampleError("Each of the two source TODOs must survive exactly once")
    for key, document in [("guide1", "chapter-organization.md"), ("guide2", "evidence-checklist.md")]:
        if not (example / "references" / document).is_file() or "\\cite{" + key + "}" not in body:
            raise ExampleError("The cited original teaching documents must be present")
    if body.count("\\chapter{") != 3 or "\\label{eq:mean}" not in body or "\\label{fig:workflow}" not in body:
        raise ExampleError("The reviewed three-chapter, equation and figure structure is incomplete")
    return calculated


def require_tools() -> dict[str, str]:
    found = {name: compiler.find_executable(name) for name in ("latexmk", "xelatex", "bibtex")}
    missing = [name for name, path in found.items() if not path]
    if missing:
        raise ExampleError("Missing TeX tools: " + ", ".join(missing) + "; see the example README")
    versions = {"platform": platform.platform(), "python": platform.python_version()}
    for name, path in found.items():
        result = subprocess.run([path, "--version" if name != "latexmk" else "-v"], capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise ExampleError("Cannot run " + name + ": " + result.stderr.strip())
        versions[name] = result.stdout.strip()
    return versions


def run_step(folder: Path, stage: str, script: str, *arguments: str) -> dict[str, object]:
    command = [sys.executable, str(SCRIPTS / script), *map(str, arguments)]
    timeout = compiler.DEFAULT_TIMEOUT + 30 if script == "compile_thuthesis_project.py" else 120
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    (folder / (stage + ".json")).write_text(result.stdout, encoding="utf-8")
    with (folder / "commands.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"stage": stage, "command": command, "returncode": result.returncode, "stderr": result.stderr}, ensure_ascii=False) + "\n")
    if result.returncode:
        raise ExampleError(f"{stage} failed (exit {result.returncode}); see {folder / (stage + '.json')}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ExampleError(stage + " did not produce a JSON report") from exc
    if payload.get("ok") is False:
        raise ExampleError(stage + " reported ok=false")
    return payload


def check_preserved(project: Path, before: dict[str, str], case: str) -> dict[str, object]:
    allowed = set(TARGETS) | {"main.tex"}
    if case == "cited":
        allowed.add("ref/refs.bib")
    changed = [name for name, sha in before.items() if name not in allowed and (not (project / name).is_file() or digest(project / name) != sha)]
    if changed:
        raise ExampleError("Unexpected changes to template files: " + ", ".join(changed))
    return {"ok": True, "checked_files": len(set(before) - allowed), "allowed_changes": sorted(allowed), "unexpected_changes": changed}


def run_case(output: Path, archive: Path, lock: dict[str, str], case: str) -> dict[str, object]:
    folder = output / case
    folder.mkdir()
    reports = folder / "reports"
    reports.mkdir()
    project = folder / "project"
    baseline = folder / "baseline"
    chapters = [arg for target in TARGETS[1:] for arg in ("--chapter", target)]
    run_step(reports, "initialization", "init_thuthesis_project.py", project, "--source", archive,
             "--sha256", lock["sha256"], "--main", "main.tex", *chapters)
    run_step(reports, "inspection", "inspect_thuthesis_project.py", project)
    run_step(reports, "targets", "validate_tex_targets.py", project, *TARGETS, "ref/refs.bib", "--allow-bibliography")
    before = {p.relative_to(project).as_posix(): digest(p) for p in sorted(project.rglob("*")) if p.is_file()}
    write_json(reports / "template-before.json", before)
    for path in [project / p for p in TARGETS] + sorted((project / "ref").glob("*.bib")) + [project / "main.tex"]:
        saved = baseline / path.relative_to(project)
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)
    for relative in ["main.tex", *TARGETS]:
        text = (EXAMPLE / "expected" / relative).read_text(encoding="utf-8")
        if case == "no-citations":
            text = text.replace("\\cite{guide1}", "").replace("\\cite{guide2}", "")
            if relative == "main.tex":
                # Keep \bibliography: this is the real bibdata-with-zero-citations regression.
                text = text.replace("原创教学示例\\par", "原创教学示例（无引用回归变体）\\par")
        (project / relative).write_text(text, encoding="utf-8")
    if case == "cited":
        args = [project, "ref/refs.bib", "--entries-file", EXAMPLE / "references/guide.bib"]
        run_step(reports, "bibliography-dry-run", "merge_bibliography_entries.py", *args)
        run_step(reports, "bibliography-append", "merge_bibliography_entries.py", *args, "--in-place")
    quality_args = [project, *TARGETS, "--main", "main.tex", "--baseline-root", baseline,
                    "--source-backed", "--skip-preservation", "--preservation-skip-reason",
                    "Explicitly replace official demonstration chapters with the reviewed original teaching fixture; template files and bibliography are audited separately."]
    if case == "cited":
        quality_args += ["--bibliography-targets", "ref/refs.bib"]
    quality = run_step(reports, "quality", "run_quality_gates.py", *quality_args)
    todo = quality.get("main_todo_status", {})
    if quality.get("submission_ready") is not False or todo.get("todo_count") != 2 or not todo.get("audit_complete"):
        raise ExampleError("Expected two TODOs, complete traversal and submission_ready=false")
    compile_result = run_step(reports, "compile", "compile_thuthesis_project.py", project, "--main", "main.tex")
    if not compile_result.get("compile_ok") or not compile_result.get("artifact_freshness", {}).get("pdf"):
        raise ExampleError("A fresh, successfully compiled PDF is required")
    bibliography = compile_result["bibliography_artifacts"]
    expected_keys = ["guide1", "guide2"] if case == "cited" else []
    if sorted(bibliography["citation_keys"]) != expected_keys or not bibliography["ok"]:
        raise ExampleError("Unexpected citation coverage or failed bibliography audit")
    if case == "no-citations" and bibliography["bibliography_requested"]:
        raise ExampleError("Zero citations must not require bibliography artifacts")
    log = (project / "main.log").read_text(encoding="utf-8", errors="replace")
    problems = [line for line in log.splitlines() if LOG_ERRORS.search(line)]
    write_json(reports / "log-audit.json", {"ok": not problems, "issues": problems})
    if problems:
        raise ExampleError("Missing glyphs, unresolved references or layout overflow; see log-audit.json")
    preservation = check_preserved(project, before, case)
    write_json(reports / "template-preservation.json", preservation)
    return {"ok": True, "compile_ok": True, "submission_ready": False, "todo_count": 2,
            "citation_keys": expected_keys, "pdf": f"{case}/project/main.pdf",
            "pdf_sha256": digest(project / "main.pdf"), "template_preservation": preservation}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory; existing paths are never overwritten")
    parser.add_argument("--source", type=Path, help="Official thuthesis-v7.7.1.zip (SHA-256 must match template.json)")
    parser.add_argument("--case", choices=["cited", "no-citations", "all"], default="all")
    args = parser.parse_args(argv)
    output = args.output.absolute()
    report: dict[str, object] = {"ok": False, "mode": "reviewed_fixture_replay", "cases": {}}
    created = False
    try:
        if output.exists() or output.is_symlink():
            raise ExampleError("Output already exists; choose a new directory: " + str(output))
        lock = json.loads((EXAMPLE / "template.json").read_text(encoding="utf-8"))
        if lock["version"] != "7.7.1" or lock["fontset"] != "fandol" or lock["url"] != initializer.release_url(lock["version"]):
            raise ExampleError("Unexpected template version, fontset or download URL")
        report["calculation"] = validate_materials()
        report["input_sha256"] = input_hashes()
        report["template"] = lock
        if args.source:
            if not args.source.is_file() or args.source.suffix.lower() != ".zip":
                raise ExampleError("--source must be an official release ZIP file")
            initializer.verify_sha256(lock["sha256"], digest(args.source))
        report["environment"] = require_tools()
        revision = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
        report["source_commit"] = revision.stdout.strip() if revision.returncode == 0 else None
        report["runtime_sha256"] = {p.relative_to(ROOT).as_posix(): digest(p) for p in [ROOT / "SKILL.md", Path(__file__), *sorted(SCRIPTS.glob("*.py"))]}
        with tempfile.TemporaryDirectory(prefix="thuthesis-example-") as temporary:
            archive = args.source.resolve() if args.source else Path(temporary) / "thuthesis-v7.7.1.zip"
            if not args.source:
                _, sha = initializer.download_release(lock["version"], archive, 90)
                initializer.verify_sha256(lock["sha256"], sha)
            output.mkdir(parents=True, exist_ok=False)
            created = True
            write_json(output / "result.json", report)
            run_step(output, "extraction", "extract_source_document.py", EXAMPLE / "source.md")
            for case in (["cited", "no-citations"] if args.case == "all" else [args.case]):
                report["cases"][case] = run_case(output, archive, lock, case)
                write_json(output / "result.json", report)
        if input_hashes() != report["input_sha256"]:
            raise ExampleError("Example inputs changed during replay")
        report.update(ok=True, inputs_unchanged=True)
    except (ExampleError, initializer.InitializationError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        report["error"] = str(exc)
    if created:
        write_json(output / "result.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
