# Citation And Evidence Rules

Allowed citation sources:

- Existing keys in the user's `.bib` files.
- Citation keys already present in the user's `.tex` files.
- Keys explicitly provided by the user in the current task.
- Numbered references supplied in the source material, if converted to deterministic keys and `.bib` entries without adding unsupported metadata.

Disallowed:

- Inventing keys such as `Smith2024`, `Wang2023`, `ref1`, or `todo`.
- Claiming a source exists without a provided `.bib` entry or user-provided reference.
- Writing exact experiment numbers not present in the input.
- Storing an entire supplied reference only in `note`, `abstract`, or `annote`. ThuThesis bibliography styles may omit those fields and render the cited item as `[Z]`.

Evidence handling:

- When source material uses numbered markers such as `[12]`, `[1, 2]`, `[1-3]`, `[1，2]`, `［1］`, or `【1】` and includes a numbered reference list, normalize markers to stable keys such as `\cite{<topic>12}` and generate matching `.bib` entries from the supplied reference text. Use `scripts/normalize_numeric_citations.py` for deterministic conversion when needed.
- The normalizer preserves balanced native Markdown `$...$` / `$$...$$` math, inline code, and fenced code blocks, so intervals and array indices inside them are not treated as citations. It also preserves numbered reference-list lines; review ambiguous bracketed numbers in ordinary prose before applying an in-place conversion.
- If writing into an existing ThuThesis project, validate the bibliography target with `scripts/validate_tex_targets.py --allow-bibliography`, copy it into the pre-edit baseline, then use `scripts/merge_bibliography_entries.py` in dry-run mode and again with `--in-place`. The helper appends only new keys, refuses collisions, and rejects generated `@string` / `@preamble` / `@comment` directives, so existing bytes remain untouched.
- Prefer structured BibTeX fields when the supplied source supports them. If metadata is incomplete, use a conservative `@misc` entry and preserve the supplied reference text in `title`; omit unknown fields rather than inventing author, year, venue, or URL. A normal `note` may supplement otherwise renderable fields, but it must not carry the only renderable content.
- Escape a supplied reference string for a BibTeX value with `scripts/escape_latex_text.py --bib` before placing it inside `title = {{...}}`. This escapes syntax; it does not infer metadata.
- If a claim needs support but no evidence is supplied, write `[TODO: 补充文献依据或实验结果]`.
- If a result is described qualitatively without numbers, keep it qualitative and mark missing metrics.
- If figures or tables are mentioned but not provided, create a TODO rather than a fake environment.
- If variables are used before definition, add `[TODO: 定义变量 ...]`.

Snapshot every existing direct `ref/*.bib` file, then run `scripts/run_quality_gates.py ... --bibliography-targets ref/refs.bib --baseline-root <baseline>` after an edit. Even when no bibliography file should change, keep the snapshot so the wrapper can reject undeclared mutations; `scripts/check_bibliography_consistency.py` alone does not prove preservation. Treat `bib_parse_error`, `invalid_appended_bibliography_content`, `note_only_cited_entry`, and `non_renderable_cited_entry` as blocking issues. Missing `author`, `title`, or `year` on an otherwise renderable cited entry is a warning: report it, but do not fabricate metadata to silence it.

When compile validation is authorized, also require `scripts/compile_thuthesis_project.py` to pass its `bibliography_artifacts` checks. Static key resolution alone cannot show how the selected bibliography style renders an entry; inspect `.blg` and `.bbl` coverage, empty `\bibitem` output, and entries reduced to `[Z]`.

For academic rewriting, source-backed meaning is more important than fluent wording.
