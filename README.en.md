# ThuThesis Authoring

**Turn research material into editable, verifiable ThuThesis thesis drafts.**

[中文](README.md) | English · [Download](https://github.com/peta-webster/thuthesis-authoring/releases/latest) · [Skill instructions](SKILL.md)

`thuthesis-authoring` is a general-purpose thesis authoring skill for Agents that support `SKILL.md`. It initializes projects from a specified official ThuThesis release, organizes research notes, Chinese drafts, DOCX, Markdown, or plain text into thesis sections, and helps check LaTeX, citations, structural preservation, and missing information.

The workflow stays grounded in user-provided material. It preserves research meaning, equations, figures, tables, and citations, marks missing evidence and unresolved details with `[TODO: ...]`, and delivers a thesis project the author can continue editing.

## Features

| Capability | Description |
| --- | --- |
| Project initialization | Create a new project from an exact release or a local release package, preserve template core files, and generate a user main file. |
| Source ingestion | Read `.docx`, `.md`, and `.txt`; prefer Pandoc for DOCX with a Python standard-library fallback. |
| Thesis organization | Help draft Chinese and English abstracts, introductions, and chapters, or revise selected sections. |
| Structural preservation | Snapshot existing targets and check whether equations, figures, tables, labels, and citations survive editing. |
| Bibliography handling | Normalize numbered citations, draft conservative BibTeX entries from supplied reference text, and validate entries and append operations. |
| Quality checks | Check write paths, LaTeX structure, TODOs, citation consistency, and bibliography artifacts; report submission readiness separately. |
| Compile validation | Run `latexmk` / XeLaTeX in a trusted project with a working TeX environment, then check fresh PDF and bibliography artifacts. |

## Installation

Download or clone this repository, then configure the complete directory using your Agent's skill-loading mechanism. To execute the workflow, the Agent needs access to local files and the ability to run Python scripts.

```bash
git clone --depth 1 https://github.com/peta-webster/thuthesis-authoring.git
```

Keep the relative layout of `SKILL.md`, `scripts/`, `references/`, and `assets/` intact. Installation locations vary by Agent.

The [download page](https://github.com/peta-webster/thuthesis-authoring/releases/latest) provides two packages:

- **Full package (`.zip`)**: 50 files: 41 runtime files, 8 test files, and `LICENSE`. `SKILL.md` is at the archive root. For manual installation, extract it into a new `thuthesis-authoring/` directory.
- **Runtime package (`.skill`)**: 42 files: 41 runtime files and `LICENSE`, in ZIP format and already wrapped in a `thuthesis-authoring/` directory. Use this package when tests are not needed.

Both packages contain identical runtime files. A `SHA256SUMS.txt` release asset is provided to verify downloads.

## Example requests

Invoke the skill in your Agent and identify the source, target project, and permitted edits:

```text
Use the thuthesis-authoring skill.

Create ./my-thesis from the official ThuThesis v7.7.1 release.
Read ./research-notes.md and draft Chinese and English abstracts
plus an introduction in data/abstract.tex and data/chap01.tex.
Preserve supplied equations and citations. Mark missing information
with [TODO: ...]. Proceed with initialization, writing, and quality
checks, then report changed files and outstanding information.
```

To inspect an existing project:

```text
Use the thuthesis-authoring skill.
Inspect the current ThuThesis project and report main files,
safe write targets, sensitive pages, protected files, and warnings.
Do not edit or compile anything.
```

When you need a PDF, explicitly request compilation and confirm that the entire project and its build environment are trusted. See [usage-examples.md](references/usage-examples.md) for more requests.

## Requirements

- Core scripts: Python 3.9+, using only the standard library.
- DOCX ingestion: Pandoc is optional but recommended. The standard-library fallback has lower fidelity for complex lists, footnotes, and styling.
- PDF compilation: optional; requires `latexmk`, `xelatex`, BibTeX, ThuThesis dependencies, and appropriate fonts.
- Official release downloads: HTTPS access is required. A local release archive or directory supports offline initialization.

The ThuThesis template must be supplied or downloaded separately. The user selects the version; `v7.7.1` was used in the existing release review.

## Operating boundaries

- The primary write scope is `data/*.tex` and explicitly declared `ref/*.bib` operations. Template core files remain protected.
- Word tables, OMML equations, and embedded images require manual review. Native Markdown math and supported pipe tables can use the corresponding processing workflow.
- A successful compile does not imply submission readiness. TODOs and `BLOCKING:` example-page markers still require review and completion.
- Compilation executes code and is limited to trusted projects. Project `latexmkrc` is ignored by default, and Makefiles are not run automatically. This skill does not provide a TeX sandbox.
- Static checks cannot establish semantic fidelity or academic correctness. The author must review the result against the source material.

## Validation

The repository contains 41 runtime files and 8 regression test files covering bibliography checks, compile artifacts, source ingestion, Markdown processing, CLI compatibility, and workflow boundaries.

Publication checks on 2026-09-14: **123 existing regression tests passed**, **all 17 public CLI `--help` checks passed**, and runtime files matched the reviewed release package byte for byte.

[GitHub Actions CI](https://github.com/peta-webster/thuthesis-authoring/actions/workflows/ci.yml) runs the regression suite and every public CLI's `--help` check on pushes to the main branch and pull requests. Its four configurations cover Linux and macOS with Python 3.9 and 3.14. The aggregate `CI` check succeeds only when every configuration passes. These checks require no TeX installation and do not compile a real thesis.

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

The earlier release review completed real compilation of local ThuThesis v7.7.1 projects with and without citations. This publication rechecks packaging and regression tests; it does not repeat the full thesis end-to-end compilation. Real Windows compatibility and the online official-download end-to-end path were not verified for this publication.

## Layout

```text
thuthesis-authoring/
├── SKILL.md             # Agent workflow and operating boundaries
├── scripts/             # 17 CLIs and 6 internal modules
├── references/          # 12 reference documents
├── assets/templates/    # 5 writing and delivery templates
├── tests/               # 8 regression test files
├── LICENSE              # MIT license
├── README.md
└── README.en.md
```

## License and upstream

The code and documentation in this project are licensed under the [MIT License](LICENSE), allowing use, modification, and redistribution, including commercial use. Retain the copyright notice and license text when redistributing. Both download packages include `LICENSE`.

Upstream template: [tuna/thuthesis](https://github.com/tuna/thuthesis). This project provides an independent Agent authoring workflow and does not bundle the official ThuThesis template. Official templates and assets downloaded or supplied separately retain their upstream license.

## Codex quick install (optional)

For a first installation, run the following commands. The destination must not already exist:

```bash
mkdir -p "$HOME/.agents/skills"
git clone --depth 1 \
  https://github.com/peta-webster/thuthesis-authoring.git \
  "$HOME/.agents/skills/thuthesis-authoring"
```

For a project-specific installation, use `.agents/skills/thuthesis-authoring/` inside that project instead. See the [official OpenAI skills documentation](https://learn.chatgpt.com/docs/customization/overview#skills) for installation locations. Preserve local modifications before upgrading an existing installation.
