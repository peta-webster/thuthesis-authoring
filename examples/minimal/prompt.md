# 从原创材料重新生成 / Generate from the original material

将 `<repo>` 和 `<new-project>` 替换为实际路径；目标工程目录必须不存在。本提示词用于实际 Agent 写作，不要求读取 `expected/`。固定样稿复跑命令见 README。

```text
使用 <repo>/SKILL.md 中的 thuthesis-authoring skill。

阅读 <repo>/examples/minimal/source.md、data.json 以及 references/ 中的
两份原创说明和 guide.bib。按 source.md 的三个章节生成《学位论文写作与自查指南》，
保留中英文摘要、公式、两张表、写作流程图、引用和两个 TODO。
所有材料均为本项目原创教学内容，数值 2、4、6 只用于均值为 4 的算例。
不要补造外部论文、研究结果、个人身份或学校规定。

先执行材料提取，再使用官方 ThuThesis v7.7.1 创建 <new-project>，
校验 template.json 中的 SHA-256，指定 main.tex 和 data/chap01.tex 至 chap03.tex。
写入范围为 data/abstract.tex、这三个章节以及追加式 ref/refs.bib 操作。
允许替换本次新建工程中的官方示例摘要和章节；先留存 baseline，
质量门中说明跳过原示例 TeX 结构比较的原因，仍检查文献与核心文件保全。

本示例明确允许配置新建的 main.tex：使用 Fandol，制作原创教学说明页，
仅装配摘要、目录、三章与参考文献。不要装配官方示例身份、委员会、简历、
评语、决议和声明页；不要改动模板核心文件或敏感页面正文。
主文件的调整属于本示例明确授权的装配操作，不是修改模板核心。

使用已审查的官方模板和本次新写的内容，执行质量门及真实编译。
不启用工程自带 latexmkrc 或 Makefile，不自动安装工具。
最后报告输入哈希、章节映射、修改文件、文献保全、两个 TODO、
compile_ok 和 submission_ready，并逐页检查 PDF 的公式、表格和流程图。
```

Replace `<repo>` and `<new-project>` with local paths. The destination must not exist. This prompt requests a real authoring run from original inputs, not a replay of `expected/`.

```text
Use the thuthesis-authoring skill in <repo>/SKILL.md.
Read examples/minimal/source.md, data.json, and the two original supporting
notes and guide.bib in references/. Produce the three-chapter Chinese guide
with both abstracts, its equation, two tables, workflow figure, citations,
and exactly the two unresolved TODOs. Values 2, 4, and 6 are illustrative;
their mean is 4. Do not invent papers, findings, identities, or institutional rules.

Extract the source first. Initialize <new-project> from official ThuThesis
v7.7.1, verifying the checksum in template.json. Select main.tex and
data/chap01.tex through chap03.tex. Write data/abstract.tex and those chapters;
append guide.bib to ref/refs.bib without replacing existing entries.
Replacing the newly initialized demonstration abstract and chapters is
authorized. Save a baseline first and report the reason for skipping their
old TeX structures; continue auditing bibliography and template preservation.

For this example, configuring the new main.tex is authorized: use Fandol,
an original teaching title page, abstracts, contents, three chapters and
bibliography. Omit upstream identity/process/example pages from assembly.
Do not change template core files or sensitive page bodies.

Run quality gates and actual compilation on these reviewed inputs without
enabling project latexmkrc or Makefile behavior or installing tools silently.
Report input hashes, chapter mapping, edits, preservation, both TODOs,
compile_ok and submission_ready. Visually review every PDF page.
```
