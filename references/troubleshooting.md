# Troubleshooting

## Skill Does Not Trigger

Use the explicit trigger:

```text
使用 thuthesis-authoring skill
```

or:

```text
Use the thuthesis-authoring skill
```

Then describe the project root, target files, and source material.

## Project Is Not Detected

Run:

```bash
python3 <skill-root>/scripts/inspect_thuthesis_project.py /path/to/project
```

Check whether the project has a `.tex` main file with:

- `\documentclass{thuthesis}` or `\documentclass[...]{thuthesis}`
- `\begin{document}`
- `\input{data/...}` entries

## Target File Is Blocked

Run:

```bash
python3 <skill-root>/scripts/validate_tex_targets.py /path/to/project data/chap01.tex
```

Common blocked targets:

- `thusetup.tex`
- `thuthesis.cls`
- `latexmkrc`
- `Makefile`
- bibliography style files
- `data/committee.tex`, `data/comments.tex`, `data/resolution.tex`, `data/resume.tex`

For sensitive `data/` files, only use `--allow-sensitive-data` after explicit user confirmation.

## Bibliography Is Empty Or Citations Are Undefined

Run a project-level citation check before relying on a full compile:

```bash
python3 <skill-root>/scripts/check_bibliography_consistency.py /path/to/project
```

If only a few files were generated, pass those targets explicitly:

```bash
python3 <skill-root>/scripts/check_bibliography_consistency.py /path/to/project data/chap01.tex data/chap02.tex
```

Common causes:

- Generated `\cite{...}` keys were not written to `ref/refs.bib`.
- Generated `ref/refs.bib` replaced the template's original bibliography instead of being merged into it.
- Source text used numbered references but the converted draft kept `[12]` as plain text instead of generating matching BibTeX entries.
- A `.bib` entry has unbalanced braces or quotes and therefore produces `bib_parse_error`.
- The cited entry stores its entire reference in `note`, `abstract`, or `annote`, which produces `note_only_cited_entry` or `non_renderable_cited_entry`.

Do not invent missing citation metadata. If a source reference is incomplete, keep the supplied reference text in the `title` of a conservative `@misc` entry and omit unknown fields. A `note` is acceptable only as supplemental content beside fields the bibliography style renders.

## Bibliography Renders As `[Z]`

A key can pass a simple existence check while the selected ThuThesis bibliography style has no field it can display. A note-only entry is the common cause because the style may omit `note`.

First run the static check above and fix `note_only_cited_entry`, `non_renderable_cited_entry`, or `bib_parse_error`. Then run trusted compile validation and inspect the structured result:

```bash
python3 <skill-root>/scripts/compile_thuthesis_project.py /path/to/project
```

`compile_ok: true` means the TeX command produced the PDF. Completion still requires `bibliography_artifacts.ok: true`; when the current `.aux` requests a bibliography, it checks readable `.blg` / `.bbl` files, cited-key coverage, empty `\bibitem` bodies, and `[Z]` output. The top-level `ok` is false when a required bibliography artifact check fails. If the current `.aux` requests no bibliography, leftover files are identified by `bbl.stale` / `blg.stale` with `audit_skipped: true` and reported as `stale_bibliography_artifact` advisories instead of current-build failures.

The compile helper forces a rebuild and reports `artifact_freshness`. A command that returns zero without refreshing the expected PDF fails; pre-existing PDF/AUX/BBL/BLG symbolic links are rejected before any build starts. On POSIX systems, a timeout terminates the whole compile process group so TeX descendants cannot continue writing after the helper returns.

## Markdown Table Is Not Converted

Check `conversion_candidates` from `extract_source_document.py`. Only valid native Markdown pipe tables with plain-prose/math cells are candidates; outer pipes are optional. A Word table remains `manual_review` even when Pandoc represents it with pipes. An invalid delimiter, unequal row width, or cell containing an image, footnote, inline code, emphasis/strong markup, inline or reference-style Markdown link, or raw HTML also remains manual review so no row or nested object is truncated or flattened. Structural reason codes recommend the converter after repair; nested-object reason codes require manual table object review.

File arguments are a dry run by default and print only a JSON summary:

```bash
python3 <skill-root>/scripts/convert_markdown_tables.py notes.md
```

Use `--in-place` to rewrite a reviewed file, or use `--text` / stdin to print converted content. Convert related files in one invocation to keep generated labels unique.

## Escaped Dollar Breaks Math-Aware Conversion

Use the shared math-aware scanner instead of manually removing backslashes:

```bash
python3 <skill-root>/scripts/escape_latex_text.py --math-aware --text '$C_{\min}=\$0.71$ 和 $C_{\max}=\$1.71$'
```

Both balanced math spans must remain intact. `\$` inside math is part of that span, and an escaped or unmatched dollar in prose must remain a literal instead of opening a span that consumes a later formula. If the output crosses formula boundaries, stop and report the source range; do not repair it by globally deleting `\$` or `\|`.

## Compile Fails On macOS Fonts

Compile only a project the user confirms is trusted. The helper disables project `latexmkrc` behavior by default and does not run a project Makefile. Use `--allow-project-build-config` only after explicit confirmation because those files can execute local commands.

ThuThesis may auto-detect the mac fontset and require fonts such as `Kaiti SC Regular`. If unavailable, test with a copy of the project and change:

```tex
\documentclass[degree=master]{thuthesis}
```

to:

```tex
\documentclass[degree=master,fontset=fandol]{thuthesis}
```

Do not silently change the user's template. Report the font issue first.

## MacTeX Is Installed But Tools Are Not Found

The compile script checks `/Library/TeX/texbin` automatically. Manual shell commands may need:

```bash
export PATH=/Library/TeX/texbin:$PATH
```

## Claim Audit Reports Too Many Unsupported Claims

For newly generated thesis text, keep the warnings and add evidence or `[TODO: ...]`.

For faithful conversion from a supplied paper, translation, or source-backed document, run:

```bash
python3 <skill-root>/scripts/check_todo_and_claims.py --source-backed data/chap01.tex
```

This still checks TODO format and suspicious citation keys, but skips unsupported-claim warnings.
