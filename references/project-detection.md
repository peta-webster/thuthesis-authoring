# Project Detection

For local projects, inspect before editing.

Detection signals:

- A `.tex` file contains `\documentclass[...]{thuthesis}` or `\documentclass{thuthesis}`.
- A main file inputs `thusetup.tex`.
- A main file contains `\input{data/abstract}` and `\input{data/chap..}`.
- The project has `data/`, `ref/`, `thusetup.tex`, and ThuThesis style files.
- Official release-like projects often include `thuthesis.cls`, `thuthesis.pdf`, `thuthesis-example.pdf`, `thu-fig-logo.pdf`, `thu-text-logo.pdf`, `ref/refs.bib`, and `thuthesis-*.bst/.bbx/.cbx` files.

Do not assume the main file name. The inspector scans the project tree. If the selected main file is not a root-level auto-detection candidate, pass its project-relative path to the compile helper with `--main`.

When several main files exist, prefer the file that:

1. Uses the `thuthesis` document class.
2. Contains `\begin{document}`.
3. Inputs `thusetup`.
4. Inputs multiple `data/*.tex` files.

Use `scripts/inspect_thuthesis_project.py <project-root>` to produce a JSON project summary. Treat warnings as planning inputs, not immediate failures.

Important output fields:

- `safe_targets`: default editable thesis content files.
- `sensitive_data_files`: official process or personal-information files under `data/` that need explicit confirmation.
- `protected_files`: template, style, build, logo, manual, and asset files that should not be edited by this skill.
- `is_official_release_like`: true when the project contains several official release signals.
