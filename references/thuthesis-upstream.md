# ThuThesis Upstream

Known official sources:

- Official project and development repository: https://github.com/tuna/thuthesis
- GitHub Releases: https://github.com/tuna/thuthesis/releases
- CTAN package: https://www.ctan.org/pkg/thuthesis
- TUNA release mirror: https://mirrors.tuna.tsinghua.edu.cn/github-release/tuna/thuthesis/
- Online usage scenarios: TeXPage and Overleaf templates

As checked against the official GitHub/CTAN sources on 2026-08-19, the latest published release was `v7.7.1`, dated 2026-05-26, with release asset `thuthesis-v7.7.1.zip`. Exact-version assets follow `https://github.com/tuna/thuthesis/releases/download/v<VERSION>/thuthesis-v<VERSION>.zip`. Re-check upstream when current version or exact template facts matter.

ThuThesis is a Tsinghua University thesis LaTeX template for undergraduate thesis training, master's theses, doctoral dissertations, and postdoctoral reports. The official README recommends using published releases for normal users because they include the manual and example documents.

Common current repository paths include:

- Main/example: `thuthesis-example.tex`
- Setup: `thusetup.tex`
- Class/source: `thuthesis.dtx`, `thuthesis.ins`
- Bibliography styles: `thuthesis-*.bst`, `thuthesis-*.bbx`, `thuthesis-*.cbx`
- Data files: `data/abstract.tex`, `data/acknowledgements.tex`, `data/appendix.tex`, `data/chap01.tex`, `data/chap02.tex`, `data/chap03.tex`, `data/chap04.tex`, `data/comments.tex`, `data/committee.tex`, `data/denotation.tex`, `data/resolution.tex`, `data/resume.tex`
- Bibliography database: `ref/refs.bib`
- Build files: `latexmkrc`, `Makefile`, `build.lua`
- Assets and manuals: `figures/*.pdf`, `thu-fig-logo.pdf`, `thu-text-logo.pdf`, `thuthesis.pdf`, `thuthesis-example.pdf`

Use these paths as detection hints only. The user's local project may be based on a release zip, CTAN install, Overleaf export, or a customized fork.

The v7.7.1 release inspected during development included `thuthesis.cls`, `thuthesis.dtx`, `thuthesis.ins`, `latexmkrc`, `Makefile`, bibliography style files, logo PDFs, manuals, `figures/`, `ref/refs.bib`, and the official `data/` files listed above. That fixture is not bundled with this Skill; revalidate any supplied release. This skill edits thesis content files, not template core files.
