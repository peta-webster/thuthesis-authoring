# Quality Gates

Run every gate below in one pass:

```bash
python3 <skill-root>/scripts/run_quality_gates.py \
  <project-root> <target...> --baseline-root <pre-edit-baseline-root> \
  --main <user-main.tex>
```

Create the baseline before editing, outside the user project, and preserve each target's project-relative path. Snapshot every existing direct `ref/*.bib` file too, even if no bibliography edit is planned; this lets the wrapper reject an omitted `--bibliography-targets` declaration. The TeX preservation gate compares headings, labels, references, citations, captions, and figure/table/equation-like environments.

Flags: `--main <root-main.tex>` (audit the explicitly selected main and literal project-local `\input` / `\include` graph for TODOs), `--source-backed` (faithful conversion), `--skip-bibliography` (no citations or `.bib` touched), `--allow-sensitive-data` (explicit confirmation), and `--bibliography-targets <ref/*.bib...>` (validate changed databases and require append-only baseline preservation). Multiple main files are never guessed: pass the intended root-level main explicitly. For an entirely new TeX target or user-confirmed structural deletion, use `--skip-preservation --preservation-skip-reason <reason>` together with the required `--baseline-root`; this skips only TeX structural comparison and does not skip bibliography preservation. Use `--allow-existing-bibliography-changes --bibliography-change-reason <reason>` only when the user explicitly requested correction of existing bibliography content.

The command exits non-zero and lists `failed_gates` when any structural gate fails. `submission_ready` is deliberately separate: it is false when the selected-main graph contains an active, commented, literal-text, or `BLOCKING:` TODO, or when that graph cannot be resolved completely. Valid TODOs do not make `ok` false or change compile success. If `--main` is omitted, `submission_ready` is null and `main_todo_status.audit_skipped` explains why. Use the individual checkers only when isolating one gate. The bibliography gate uses a brace- and quote-aware BibTeX parser; it fails on parse errors, duplicate or missing keys, cited note-only entries, and cited entries with no fields the style can render. Missing common metadata on an otherwise renderable entry is reported under warnings and does not justify invented values.

Before reporting completion, check:

1. Target paths were validated.
2. Protected template files were not modified.
3. LaTeX environments and braces are roughly balanced.
4. TODO markers use `[TODO: ...]`.
5. Citations are from supplied sources or marked as TODO.
6. When citations or `.bib` files were touched, every generated or preserved `\cite{}` key resolves to a parseable, renderable entry in the project `.bib` files; no cited entry stores all content only in `note`, `abstract`, or `annote`.
7. All current versus baseline `ref/*.bib` changes were declared. Existing `.bib` bytes remain an exact prefix after append-only merging, and the suffix contains only new entries (no `@preamble`, `@string`, `@comment`, or unparsed content). Any user-requested existing-entry correction is explicitly reported as a skipped append-only check while the declaration audit remains active.
8. Strong claims have nearby evidence, citations, numeric results, or TODO markers.
9. Existing labels, refs, cites, captions, figures, tables, and equations were not silently removed.
10. Missing information and assumptions are listed for the user.
11. For generated projects, `main_todo_status.audit_complete` is true and `submission_ready` is reported. Any TODO keeps it false even if all structural gates pass.
12. If compile validation ran, `compile_ok` is true and, when the current `.aux` requests a bibliography, `bibliography_artifacts` passes `.blg` / `.bbl` readability, cited-key coverage, non-empty `\bibitem` content, and `[Z]` checks. The top-level compile result must remain false when required artifact checks fail even if the TeX command returned success. If no bibliography is requested, pre-existing files are marked with `bbl.stale` / `blg.stale` and `audit_skipped` rather than treated as output from the current build.

These gates are structural and heuristic. They do not prove that rewritten prose is semantically faithful, academically correct, or complete. Compare the final diff with the source material and disclose any unverified interpretation.

Compile validation is optional and environment-dependent. If compile tools are absent, state that only structural and static bibliography checks were run. If compilation runs, report the command result and the bibliography-artifact result separately.
