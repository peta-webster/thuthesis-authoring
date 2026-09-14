# Chapter Mapping

Map rough material conservatively:

- Research background, motivation, problem importance -> introduction chapter, often `data/chap01.tex`.
- Literature notes and comparison with existing work -> related work or background chapter, often `data/chap02.tex`.
- Model, algorithm, system design, variables, assumptions -> method chapter.
- Dataset, experiment setup, metrics, baselines, implementation details -> experiment chapter.
- Numeric results, ablations, error analysis, case studies -> results and analysis chapter.
- Summary, limitations, future work -> conclusion chapter.
- Chinese and English abstract drafts -> `data/abstract.tex`.

If the local project already has chapter titles, follow them instead of imposing this generic mapping.

For multi-chapter generation, first produce:

- Source material groups.
- Target files.
- Proposed chapter/section titles.
- Missing evidence list.
- Files that will not be touched.
