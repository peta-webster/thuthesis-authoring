# Sample User Requests

## Initialize Only

```text
使用 thuthesis-authoring skill。

请从官方 ThuThesis v7.7.1 发布版创建一个空项目到 ./my-thesis-clean。
目标目录必须不存在；本次不要填充 data/*.tex，也不要编译。
初始化并检查完成后，报告版本、下载来源、SHA-256、目标路径和结构验证结果，然后停止。
```

## Initialize A New Project

```text
使用 thuthesis-authoring skill。

请从官方 ThuThesis v7.7.1 发布版创建一个全新项目到 ./my-thesis。
目标目录必须不存在；保留官方许可证和全部模板文件。
初始化后只填充 data/abstract.tex 和 data/chap01.tex，缺失信息使用 [TODO: ...] 标注。

材料：
[粘贴研究笔记或提供 DOCX / Markdown 文件]
```

## Inspect Only

```text
使用 thuthesis-authoring skill。

请检查当前目录中的 ThuThesis 项目。
不要修改任何文件。
请输出 main_files、safe_targets、sensitive_data_files、protected_files 和 warnings。
```

## Convert Notes To Introduction

```text
使用 thuthesis-authoring skill。

当前目录是 ThuThesis 项目根目录。
只允许修改 data/chap01.tex。
请把下面材料整理为“绪论”草稿，包括研究背景、研究问题、研究目标、本文工作和章节安排。
缺少文献、实验数据或定义时，用 [TODO: ...] 标出。

材料：
[粘贴研究笔记]
```

## Generate Abstract

```text
使用 thuthesis-authoring skill。

只允许修改 data/abstract.tex。
请根据以下章节草稿生成中文摘要和英文摘要。
不要编造实验结果。没有数据的位置用 [TODO: 补充实验结果]。
关键词不超过 5 个。

材料：
[粘贴章节摘要或论文概要]
```

## Rewrite Existing Section

```text
使用 thuthesis-authoring skill。

目标文件：data/chap02.tex
请只改写“相关工作”这一节，使语言更符合学位论文表达。
保留所有 \cite、\ref、\label、公式、图表环境和小节标题。
不要新增未经提供的引用。
```

## Source-Backed Markdown Conversion

```text
使用 thuthesis-authoring skill。

输入是一篇已有论文/翻译稿 Markdown。
请把它转换进官方 ThuThesis 项目的 data/*.tex 文件。
这是 source-backed conversion：若原文包含编号参考文献，请从原文条目生成保守 `.bib` 草案，并把正文 `[n]`、`[1，2]`、`[1-3]`、`［n］`、`【n】` 等编号引用转为 `\cite{}`；不要补造未提供的引用元数据。
转换后运行 check_todo_and_claims.py --source-backed。
```

建立 baseline 时复制所有现有的直接 `ref/*.bib` 文件。如果转换还会新增 `ref/refs.bib` 条目，用 `merge_bibliography_entries.py` dry-run/`--in-place` 追加，并在质量门中传入 `--bibliography-targets ref/refs.bib`。新建 TeX 文件时可同时传 `--baseline-root` 与 `--skip-preservation`：后者只跳过新 TeX 的结构保全，不会跳过 `.bib` 检查。

## Compile And Report

```text
使用 thuthesis-authoring skill。

请编译当前 ThuThesis 项目。
如果失败，请区分：
1. TeX 环境或字体问题；
2. 模板文件问题；
3. 本次生成内容导致的 LaTeX 错误。
请给出第一个阻塞错误和相关文件路径。
```
