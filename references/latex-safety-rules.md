# LaTeX Safety Rules

Safe default targets:

- `data/abstract.tex`
- `data/chap*.tex`
- `data/appendix*.tex`
- `data/acknowledgements.tex`
- `data/denotation.tex` when the user provides symbol definitions.
- New files under `data/` when they are referenced by the user's chosen main file or explicitly requested.

Sensitive official `data/` targets:

- `data/committee.tex`
- `data/comments.tex`
- `data/resolution.tex`
- `data/resume.tex`

These files may contain process-specific committee information, supervisor comments, defense resolutions, or personal resume/publication records. Do not edit them by default. Require explicit user confirmation and run `validate_tex_targets.py --allow-sensitive-data ...` before editing.

Protected targets (outside this Skill even when the user names them; use a separately scoped template-maintenance workflow):

- `thuthesis.cls`, `thuthesis.dtx`, `thuthesis.ins`
- `thusetup.tex`
- `latexmkrc`, `Makefile`, `build.lua`
- `*.bst`, `*.bbx`, `*.cbx`
- `thu-fig-logo.pdf`, `thu-text-logo.pdf`, `figures/*.pdf`, manuals, generated PDFs, fonts, and template assets

Preserve:

- `\chapter`, `\section`, `\subsection` structure unless restructuring is requested.
- `\label{...}`, `\ref{...}`, `\autoref{...}`, `\cite{...}`.
- Existing figure/table/equation environments.
- Template-specific commands beginning with `\thu`.
- Math mode content.

Use `[TODO: ...]` instead of fake values. Never replace missing citations with invented keys.
