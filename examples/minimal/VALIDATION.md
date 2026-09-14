# 本地验证记录 / Local validation

验证日期：2026-09-15（Asia/Shanghai）。本记录只描述本地实际执行结果。

## 首次 Agent 生成

本次先创作了约 3,134 个中文字的三章 Markdown 正文、中英文摘要和两份教学说明，再按仓库 `SKILL.md` 执行提取、章节映射、初始化、目标验证、baseline 留存、LaTeX 写入、文献追加、质量门和真实编译。生成过程中使用了 skill 的数学感知转义、表格渲染和编号引用处理辅助函数；新建主文件的教学展示配置由本次计划明确授权。

没有导入他人的论文、译文、图表或宣传素材。两条文献确实对应本目录中提供的原创教学说明，不是虚构的外部出版物。

完整的命令记录、输入与输出哈希、章节映射、环境和结果摘要见 [first-authoring.json](first-authoring.json)。其中 `{repo}` 表示仓库根目录，`{work}` 表示本次本地输出目录；记录中的一次性写作脚本属于首次生成过程，公开复跑入口为 `tools/run_example.py`。源码基线为 `c67401817c7c14439a4013997ea2ba11f002e672`，本轮新增示例当时尚未提交，因此文件哈希用于识别实际内容。

首次写作与固定样稿复编分别记录。前者产生了 `expected/` 中的参考输出；后者使用这些输出验证流程，不代表又进行了一次 Agent 写作评测。

## 本地环境与命令

- macOS / Apple Silicon，Python 3.9.6。
- 官方 ThuThesis v7.7.1，ZIP 校验值与 GitHub Release 提供的 SHA-256 一致，见 [template.json](template.json)。
- TeX Live 2025，XeTeX 0.999997，latexmk 4.87，BibTeX 0.99d。
- Fandol 中文字体及 TeX Gyre 配套字体。首次尝试因缺少 `texgyretermes-regular` 失败；通过 TeX Live 2025 的冻结仓库安装 `tex-gyre` 后成功。未跨年份升级 TeX Live。

实际复跑方式（路径已改为可替换示例）：

```bash
# 本地官方 ZIP：两个场景均执行
python3 tools/run_example.py --output /tmp/thuthesis-example \
  --source /path/to/thuthesis-v7.7.1.zip

# 自动从指定官方 Release 下载：有引用场景
python3 tools/run_example.py --output /tmp/thuthesis-example-online --case cited

# 核心回归测试与新增本地入口检查
python3 -m unittest discover -s tests -p 'test_*.py'
```

两种模板获取路径均在本机实际通过；在线下载后的 ZIP 也使用固定 SHA-256 校验。

## 结果

| 检查 | 有引用指南 | 无引用回归变体 |
| --- | --- | --- |
| 真实编译 | 通过，A4、11 页 | 通过，A4、11 页 |
| `compile_ok` / 顶层 `ok` | `true` / `true` | `true` / `true` |
| 引用 | `guide1`、`guide2` 均渲染，BibTeX 零警告 | 零引用；主文件仍保留 `\bibliography` |
| 质量门 | 结构通过 | 结构通过 |
| TODO / 提交就绪 | 2 / `false` | 2 / `false` |
| 模板保全 | 39 个非授权修改文件保持一致 | 40 个非授权修改文件保持一致 |
| 最终日志 | 无未定义引用、缺字或溢出 | 无未定义引用、缺字或溢出 |

无引用变体刻意保留空的参考文献标题页，用于检查 `\bibdata` 存在但零引用的场景，主要展示稿采用有引用版本。

教学数据 `2、4、6` 重算得到数量 `3`、总和 `12`、均值 `4`。原始输入哈希未变化，原有 BibTeX 内容按前缀保留，新条目仅追加。初始化器对官方示例页添加的提示保留在工程中，生成后不再编辑这些页面，展示 PDF 不装配它们。官方模板核心文件保持不变。

本地测试共 **129 项通过**，包含原有 123 项和新增 6 项；17 个公开 CLI 的 `--help` 均通过。新增检查覆盖已有输出目录、悬空输出链接、错误模板校验值、缺少 TeX 和模板／敏感页意外修改；原有文献与编译测试继续覆盖缺失引用、陈旧 PDF/AUX/文献产物不能冒充当前结果等情况。

## 逐页检查与预览来源

有引用指南的 11 页均已渲染并逐页检查。检查发现 TODO 列表开头的方括号曾被 LaTeX 当作可选标签，造成左侧文字裁切；已改为正文列表项，重编后两条 TODO 完整可见。长表格采用固定宽度换行。

无引用变体的第 1、5、7、11 页已单独检查；其余 7 页渲染像素与已检查的指南页面完全一致。最终未发现裁切、重叠或缺字。

- `previews/equation-and-table.png`：有引用 PDF 第 7 页，印刷页码 3。
- `previews/workflow-and-review.png`：有引用 PDF 第 9 页，印刷页码 5。

预览直接由最终真实 PDF 渲染，未重新绘制页面或伪造编译状态。PDF 哈希标识此次产物；不同时间重编可能因元数据产生不同 PDF 哈希，复跑不要求 PDF 字节一致。

## English summary

The original three-chapter guide was authored from the supplied teaching material through this repository's skill workflow, then inspected and compiled locally. The initial Agent authoring record and the later reviewed-fixture replays are distinguished in [first-authoring.json](first-authoring.json).

Both cited and citation-free cases compiled successfully to 11-page A4 PDFs. The cited case rendered both original teaching references without BibTeX warnings. Both cases preserved two TODOs and correctly reported `submission_ready=false`. Local ZIP and official-download paths passed the pinned archive checksum. All 129 tests (123 existing plus 6 new) and 17 public CLI help checks passed locally.

Every page of the guide was visually reviewed. A clipped TODO-list layout was corrected and recompiled; the previews show the final real pages 7 and 9. Changed pages of the citation-free variant were reviewed separately and all other pages were pixel-identical. No CI workflow was added, and Linux and Windows were not tested.
