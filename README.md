# ThuThesis Authoring

**将研究材料整理为可编辑、可验证的 ThuThesis 学位论文草稿。**

中文 | [English](README.en.md) · [下载](https://github.com/peta-webster/thuthesis-authoring/releases/latest) · [Skill 指令](SKILL.md)

`thuthesis-authoring` 是一个通用的论文写作 Agent skill，可由支持 `SKILL.md` 的 Agent 加载。它可以从指定的官方 ThuThesis 发布版初始化工程，将研究笔记、中文初稿、DOCX、Markdown 或纯文本整理到论文结构中，并辅助检查 LaTeX、引用、内容保全和待补信息。

工作流以用户提供的材料为依据：保留研究含义、公式、图表和引用，用 `[TODO: ...]` 明确标记缺失证据与待确认内容，交付可继续编辑的论文工程。

## 功能

| 能力 | 说明 |
| --- | --- |
| 工程初始化 | 使用用户指定的官方版本或本地发布包创建新工程，保留模板核心文件，生成用户主文件。 |
| 材料读取 | 支持 `.docx`、`.md`、`.txt`；DOCX 优先使用 Pandoc，也可使用 Python 标准库回退。 |
| 论文组织 | 协助生成中英文摘要、绪论与分章正文，或定向修改现有章节。 |
| 内容保全 | 编辑前建立基线，检查已有公式、图表、标签和引用等结构是否保留。 |
| 文献处理 | 将编号引用规范化为 LaTeX 引用，从提供的参考文献文本生成保守 BibTeX 草案，检查条目与追加操作。 |
| 质量检查 | 验证写入路径、LaTeX 结构、TODO、引用一致性和文献编译产物；单独报告提交就绪状态。 |
| 编译验证 | 在可信工程和可用 TeX 环境中运行 `latexmk` / XeLaTeX，检查新生成的 PDF 与文献产物。 |

## 安装

下载或克隆本仓库，按所用 Agent 的 skill 加载方式配置完整目录。执行工作流需要 Agent 能读取本地文件并调用 Python 脚本。

```bash
git clone --depth 1 https://github.com/peta-webster/thuthesis-authoring.git
```

保留 `SKILL.md`、`scripts/`、`references/` 和 `assets/` 的相对目录结构。各 Agent 的安装位置可能不同。

[下载页面](https://github.com/peta-webster/thuthesis-authoring/releases/latest) 提供两种包：

- **完整包（`.zip`）**：50 个文件，含 41 个运行文件、8 个测试文件和 `LICENSE`；`SKILL.md` 位于压缩包根目录。手动安装时，将它解压到新建的 `thuthesis-authoring/` 目录。
- **运行包（`.skill`）**：42 个文件，含 41 个运行文件和 `LICENSE`，内容为 ZIP，内部已有 `thuthesis-authoring/` 目录；无需测试文件时可使用此包。

两个包的运行文件完全一致。Release 附有 `SHA256SUMS.txt`，可用于校验下载内容。

## 使用示例

在所用 Agent 中调用 skill，并提供输入文件、目标工程和允许修改的范围：

```text
使用 thuthesis-authoring skill。

请基于官方 ThuThesis v7.7.1，在 ./my-thesis 创建新工程。
阅读 ./research-notes.md，整理中英文摘要和绪论，写入
data/abstract.tex 与 data/chap01.tex。
保留已有公式和引用；缺失的信息使用 [TODO: ...] 标注。
本次执行初始化、内容写入和质量检查，完成后报告修改文件和待补信息。
```

仅检查已有工程：

```text
使用 thuthesis-authoring skill。
请检查当前 ThuThesis 工程，报告主文件、安全写入目标、
敏感页面、受保护文件和警告。不要修改或编译。
```

需要 PDF 时，可以另行明确请求编译，并确认整个工程及其构建环境可信。更多示例见 [usage-examples.md](references/usage-examples.md)。

## 环境要求

- 核心脚本：Python 3.9+，仅使用标准库。
- DOCX 读取：Pandoc 可选，但推荐使用；标准库回退对复杂列表、脚注和样式的保真度较低。
- PDF 编译：可选，需要 `latexmk`、`xelatex`、BibTeX、ThuThesis 依赖与相应字体。
- 官方版本下载：需要 HTTPS 网络访问；本地发布包或目录可用于离线初始化。

ThuThesis 模板需单独提供或下载。版本由用户指定；`v7.7.1` 是已有审查使用的模板版本。

## 使用边界

- 主要写入范围为 `data/*.tex` 和显式声明的 `ref/*.bib` 文献操作；模板核心文件保持受保护。
- Word 表格、OMML 公式和嵌入图片需要人工核对。原生 Markdown 数学与支持的管道表格可进入相应处理流程。
- 编译成功不代表可以提交：存在 TODO 或 `BLOCKING:` 示例页面标记时，仍需确认和补全。
- 编译属于代码执行，只适用于可信项目。默认忽略工程 `latexmkrc`，不自动执行 Makefile；本 skill 不提供 TeX 沙箱。
- 静态检查不能证明语义保真或学术正确性，最终内容仍需作者对照材料审阅。

## 验证

仓库包含 41 个运行文件和 8 个回归测试文件，覆盖文献检查、编译产物、材料读取、Markdown 处理、命令行兼容性和工作流边界。

2026-09-14 发布检查：现有 **123 项回归测试通过**，**17 个公开 CLI 的 `--help` 检查通过**，运行文件与经过审查的发布包逐文件一致。

[GitHub Actions CI](https://github.com/peta-webster/thuthesis-authoring/actions/workflows/ci.yml) 在主分支提交和 Pull Request 时，使用 Linux、macOS 与 Python 3.9、3.14 的四种组合运行回归测试及所有公开 CLI 的 `--help` 检查。各组合全部通过后，汇总检查 `CI` 才会成功。该检查不依赖 TeX 环境，也不执行真实论文编译。

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

此前发布审查已在本地 ThuThesis v7.7.1 上完成有引用和无引用项目的真实编译；本次发布重新检查打包与回归测试，未重新进行完整论文端到端编译。Windows 实机兼容性及官方下载的在线端到端路径未在本次发布中验证。

## 目录

```text
thuthesis-authoring/
├── SKILL.md             # Agent 工作流与使用边界
├── scripts/             # 17 个 CLI 与 6 个内部模块
├── references/          # 12 份参考说明
├── assets/templates/    # 5 个写作与交付模板
├── tests/               # 8 个回归测试文件
├── LICENSE              # MIT 许可证
├── README.md
└── README.en.md
```

## 许可证与上游

本项目的代码与文档采用 [MIT 许可证](LICENSE)，允许使用、修改和再分发，包括商业用途；再分发时请保留版权声明和许可证文本。两个下载包均附带 `LICENSE`。

模板上游：[tuna/thuthesis](https://github.com/tuna/thuthesis)。本项目提供独立的 Agent 写作工作流，不包含官方 ThuThesis 模板；单独下载或提供的官方模板及其素材保留上游许可证。

## Codex 快捷安装（可选）

首次安装可运行以下命令，目标目录必须不存在：

```bash
mkdir -p "$HOME/.agents/skills"
git clone --depth 1 \
  https://github.com/peta-webster/thuthesis-authoring.git \
  "$HOME/.agents/skills/thuthesis-authoring"
```

也可以放入工程的 `.agents/skills/thuthesis-authoring/` 目录。安装位置见 [OpenAI 官方 skills 文档](https://learn.chatgpt.com/docs/customization/overview#skills)。升级已有安装前，请先保留自己的修改。
