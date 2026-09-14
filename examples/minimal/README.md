# 学位论文写作与自查指南

中文 | [English](README.en.md) · [原创材料](source.md) · [实际生成提示词](prompt.md) · [本地验证记录](VALIDATION.md)

这是一个三章的原创教学示例，演示“Markdown 材料 → ThuThesis 章节 → 质量检查 → 真实 PDF”。正文讲解章节组织、公式与图表表达、引用和提交前自查。它是通用写作指南，不是学校官方规范，也不是可直接提交的正式学位论文。

讲解、对照句、表格、流程图和两份参考说明均为本项目新写的教学材料，采用仓库 [MIT 许可证](../../LICENSE)。数值 `2、4、6` 仅用于解释均值计算，均值为 `4`，不代表真实实验。官方 ThuThesis 模板单独下载并保留其上游许可证。

## 真实产物预览

以下两张图来自本地真实编译的 PDF，不是效果示意图。完整的页码与检查记录见 [VALIDATION.md](VALIDATION.md)。

![公式与表格页](previews/equation-and-table.png)

![流程图与自查页](previews/workflow-and-review.png)

## 两种使用方式

**重新让 Agent 写作：**按 [prompt.md](prompt.md) 的指令读取本仓库 `SKILL.md`、原创材料及配套说明，在新的目录中生成论文。Agent 的措辞可以不同，公式数值、引用来源和两项 TODO 应保持一致。首次生成的实际记录见 [VALIDATION.md](VALIDATION.md)。

**复跑已审阅样稿：**下面的命令从 `expected/` 重建固定样例，调用本仓库脚本进行初始化、文献追加、质量检查和真实编译。它不调用 Agent，也不把固定样稿的复编作为新的写作能力评测。

## 本地复跑

在仓库根目录执行。需要 Python 3.9+、`latexmk`、XeLaTeX、BibTeX，以及支持 ThuThesis 的 TeX 环境。示例采用 Fandol 中文字体与 TeX Gyre 配套字体。下载模板需要 HTTPS；使用本地发布包可以离线初始化。Markdown 读取不要求安装 Pandoc。

```bash
python3 tools/run_example.py --output /tmp/thuthesis-example
```

目标目录必须不存在。默认依次运行两个场景，约需数十秒至数分钟，取决于本地 TeX 环境：

- `cited`：三章指南，包含 `guide1` 和 `guide2` 两条对配套原创说明的引用。
- `no-citations`：同一指南的回归变体，移除上述引用命令，保留主文件的 `\bibliography`，验证存在 `\bibdata` 但零引用时的真实编译结果。该变体不作为主要展示稿。

使用已下载的官方发布包，或只运行其中一个场景：

```bash
python3 tools/run_example.py \
  --output /tmp/thuthesis-example-offline \
  --source /path/to/thuthesis-v7.7.1.zip \
  --case cited
```

`--case` 可选 `cited`、`no-citations`、`all`，默认 `all`。模板版本、官方地址和 SHA-256 固定在 [template.json](template.json)，本地 ZIP 也必须通过相同校验。

缺少字体时，先在与本机 TeX Live 年份匹配的仓库中安装 `fandol`、`tex-gyre`、`tex-gyre-math`。例如环境已配置匹配的软件源时运行 `tlmgr install fandol tex-gyre tex-gyre-math`；示例脚本不会自动安装或升级 TeX。错误报告中的原始编译输出可用于定位实际缺项。

## 输出与结果解释

```text
<output>/
├── result.json
├── extraction.json
├── commands.jsonl
├── cited/
│   ├── project/main.pdf
│   ├── baseline/
│   └── reports/
└── no-citations/
    ├── project/main.pdf
    ├── baseline/
    └── reports/
```

各 `project/` 是可编辑工程；报告保存命令、输入与运行脚本哈希、本地环境、质量检查、编译结果及模板保全检查。`source_commit` 是运行时仓库 HEAD；存在未提交内容时，应结合记录的文件哈希识别实际输入。

成功时顶层 `ok=true`，两个场景均有 `compile_ok=true`、`submission_ready=false` 和 `todo_count=2`。`submission_ready=false` 是本示例的预期结果：院系最新提交要求和导师章节意见仍待确认。数学检查、结构通过与编译成功各自提供不同的证据，不替代作者审阅。

本例明确替换新项目里的官方示例章节和摘要，因此质量门记录了跳过原示例 TeX 结构比较的原因；文献追加保全和其他模板文件保全继续检查。初始化器添加的官方示例页提示保留在工程中，展示主文件不装配这些页面；模板核心文件不改动。

目录已存在、模板校验失败、缺少工具、引用或编译失败均以非零退出码结束。执行中失败会保留已创建目录和诊断报告，供定位问题；重新运行应使用新目录。输入在运行中发生变化也会失败。

本示例仅记录本地验证，未增加 CI 工作流，未验证 Linux。公开示例与复跑工具随仓库提供；此前的 Release 下载包不包含本次新增内容。
