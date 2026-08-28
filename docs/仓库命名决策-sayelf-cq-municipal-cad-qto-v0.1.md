# 仓库命名决策：sayelf-cq-municipal-cad-qto v0.1

> 本文件是当前仓库身份的唯一命名记录。历史候选名不得作为当前仓库名、插件名或发布入口使用。

## 1. 决策结论

核心仓库名采用：`sayelf-cq-municipal-cad-qto`

中文释义：Sayelf 重庆市政 CAD 工程量计算。

本次采用的是“仓库身份名”，不是 Python 导入包名，也不是 AI 宿主插件 ID：

| 层级 | 名称 | 处理方式 |
|---|---|---|
| GitHub 仓库 | `sayelf-cq-municipal-cad-qto` | 采用本决策名 |
| Python 核心包 | `cad_qto` | 保持不变，避免破坏导入和数据作业 |
| AI 插件 ID | `municipal-cad-qto` | 保持不变，避免破坏 Codex/Claude/WorkBuddy 配置 |
| 本地工作目录 | `造价数字化` | 保持不变，避免无必要的目录迁移 |

## 2. Build Decision Record

- **真实任务**：为“重庆市政施工图纸识别及工程量计算、含挡护结构、统一 DXF 输入、人工审核闭环、跨 AI 宿主插件化”确定不易混淆的核心仓库名。
- **Step 0 分类**：`Improve`。不是重复建设新核心，而是改善已有核心的可识别性、跨平台发布准备和版本追踪。
- **现有能力比较**：当前工作区已经有唯一的 `cad_qto` 确定性核心和 `municipal-cad-qto` 插件适配层；公开 GitHub 精确检索未发现本候选名的结果。没有发现可直接复用的同名仓库身份。
- **可度量差异**：名称中明确包含 `cq`、`municipal`、`cad`、`qto` 四个检索关键词，并以 `sayelf-` 统一品牌前缀；内部包名和插件 ID 零破坏迁移。
- **最小核心**：继续使用现有 `cad_qto`、作业证据链、挡护结构规则、人工复核和 MCP 适配器，不因改名增加业务功能。
- **插件边界**：仓库名只用于项目身份和发布定位；插件协议、工具名、配置键及宿主适配层保持现状。
- **本地优先边界**：图纸、标准化 DXF、算量结果、审核记录和项目数据继续只留在项目私有目录；命名检索不携带这些内容。
- **数据分类与传输边界**：候选仓库名属于 `Public`；项目图纸、工程量结果、人员身份和密钥属于 `Internal/Restricted`，本次不向 GitHub 或其他公共网络传输。
- **GitHub 发布决策**：`Allowed`，目标公开仓库 `chuanxituzhu-lab/sayelf-cq-municipal-cad-qto` 已由维护者提供并可通过 Git 读取；仍必须在每次推送前审查 staged diff 和全部发布物。
- **状态/检查规则**：目标账号/组织下的实际仓库已经存在，名称占用已得到命名空间证据；每次后续发布仍需复核数据分类、泄漏风险和远程差异。
- **事实与判断**：
  - `Fact`：GitHub 仓库的完整身份由所有者/组织和仓库名共同组成；同名仓库可以属于不同所有者。
  - `Observation`：截至 2026-08-28，GitHub 公共精确检索未返回 `sayelf-cq-municipal-cad-qto` 的同名结果。
  - `Inference`：该名称适合作为当前项目的首选仓库名，且比 `municipal-cad-qto` 更容易区分项目品牌和重庆范围。
  - `Fact`：目标仓库 `chuanxituzhu-lab/sayelf-cq-municipal-cad-qto` 已公开可访问，当前 `main` 有 1 次许可证提交。
- **演进/回滚**：如目标命名空间冲突，保留内部包名和插件 ID，仅替换仓库身份名；如发现宿主兼容性问题，仓库名可回滚，现有插件配置无需回滚。
- **WebUI 决策**：本次不新增 WebUI；仓库命名是发布治理问题，不是施工人员工作流功能。
- **最简单实现**：新增本决策记录，并在 README 明确“仓库名 / Python 包 / 插件 ID”三者映射。
- **明确不做**：不重命名 `cad_qto`，不重命名 `municipal-cad-qto` 插件目录，不创建虚假远程 URL，不把本地项目数据上传 GitHub，不宣称已完成仓库创建。

## 3. GitHub 核验入口

- [首选名精确检索](https://github.com/search?q=sayelf-cq-municipal-cad-qto&type=repositories)
- [备用名：sayelf-municipal-cad-qto](https://github.com/search?q=sayelf-municipal-cad-qto&type=repositories)
- [备用名：sayelf-cad-quantity-takeoff](https://github.com/search?q=sayelf-cad-quantity-takeoff&type=repositories)

GitHub 的最终占用不是全站名称保留，而是“目标用户或组织命名空间下的仓库创建结果”。因此本记录把“公共精确检索无结果”标记为 `Observation`，把“目标账号可创建”保留为待确认的 `Hypothesis`。

## 4. 成功证据

1. README 明确记录 `sayelf-cq-municipal-cad-qto` 为核心仓库名。
2. `cad_qto` 和 `municipal-cad-qto` 的导入、MCP 工具和宿主配置保持兼容。
3. 现有测试、静态检查和插件边界检查不因仓库身份登记而退化。
4. 每次推送前复核目标仓库差异、待发布文件的数据分类和泄漏扫描结果。
