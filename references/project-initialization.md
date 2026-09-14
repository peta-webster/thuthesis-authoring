# Project Initialization

Use this flow only when the user asks to create a new ThuThesis project. Keep initialization separate from thesis-content editing.

## Required Inputs

- A new destination directory that does not already exist.
- Either an exact official release version, such as `7.7.1`, or a local release package/directory supplied by the user. Local sources receive strict release-layout and file-safety validation, but are not cryptographically proven official unless the user also supplies a trusted archive SHA-256.
- Initial thesis material and `data/*.tex` targets are required only when the same request also asks to populate content.

Do not silently select the newest release. If the user did not specify a version or local source, ask for one before creating the project.

## Initialize From GitHub Releases

```bash
python3 <skill-root>/scripts/init_thuthesis_project.py \
  /path/to/new-thesis --version 7.7.1 --main main.tex
```

The script downloads the exact release asset from `tuna/thuthesis`, computes its SHA-256, safely extracts it, verifies official release files, and atomically creates the destination.

## Initialize From A Local Release

```bash
python3 <skill-root>/scripts/init_thuthesis_project.py \
  /path/to/new-thesis --source /path/to/thuthesis-v7.7.1.zip --main main.tex
```

`--source` also accepts an already-extracted release-like directory. Add `--sha256 <digest>` for a local archive when the user supplies a trusted expected checksum; directory sources cannot be authenticated by one archive digest.

The initializer copies `thuthesis-example.tex` to the new user main and leaves the example unchanged. Immediately after `\input{thusetup}`, the user main overrides the official example title, author, degree, department, discipline, and supervisor values with 11 visible TODOs; optional associate-supervisor fields are cleared. This keeps `thusetup.tex` byte-identical while preventing example people from appearing as user metadata.

For a source-backed authoring request, extract and map the source first, then repeat `--chapter data/<mapped-file>.tex` for the planned chapters. Missing safe chapter targets are created as empty files for the authoring step. Without `--chapter`, conventional `data/chap*.tex` files already in the release are discovered in natural order. The main-matter inputs are replaced while the example's front matter, bibliography, optional appendix, and back matter remain assembled.

The copied denotation, appendix, and acknowledgements pages receive one ordinary example-content TODO under their generated heading. The copied committee, resume, comments, and resolution pages receive a prominent `BLOCKING:` TODO that says they must not be submitted unchanged. The initializer does not delete these pages or replace their example bodies. If any expected page or unambiguous insertion anchor is absent, initialization fails before publishing the destination.

## Safety Boundary

- Never initialize into an existing file, directory, or dangling symbolic link; do not add a force-overwrite option.
- Require the official download and every redirect target to remain on HTTPS and an approved GitHub host.
- Accept only complete release-like layouts containing the class, manual, example, setup, license, `data/`, and bibliography files. Report structural validation separately from provenance/authenticity.
- Reject unsafe archive paths, symbolic links, encrypted members, duplicate members, excessive file counts, and excessive extracted size.
- Preserve the upstream `LICENSE` and all official template assets.
- Do not edit `thuthesis.cls`, `thusetup.tex`, build files, bibliography styles, manuals, logos, or the example main file during initialization. Only the new user main, selected chapter root hints, and the seven copied example-page notices described above may differ from the release.

## Continue With Authoring

If the request was initialize-only, report the verified source, destination, and checksum, then stop. If the user also requested authoring, continue:

1. Run `<skill-root>/scripts/inspect_thuthesis_project.py <project-root>`.
2. Ask which safe `data/*.tex` targets to populate if the request is not already explicit.
3. Validate TeX targets with `<skill-root>/scripts/validate_tex_targets.py`; declare any `ref/*.bib` target with `--allow-bibliography`.
4. Save pre-edit copies of existing targets outside the new project and fill only the validated targets selected by the prior source mapping.
5. Run the standard quality gates with `--baseline-root --main <name.tex>`; distinguish structural `ok` from `submission_ready`. Compile the generated main explicitly with `compile_thuthesis_project.py <project-root> --main <name.tex>` only after the user confirms the project is trusted.

Report the exact source version or local source, destination, archive SHA-256 when available, populated files, TODOs, and validation results.
