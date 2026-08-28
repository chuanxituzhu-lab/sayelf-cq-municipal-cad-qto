# sayelf-cq-municipal-cad-qto：CAD 造价算量范围收敛决策

版本：v0.3 修订版（沿用文件名以保留已有链接）
日期：2026-08-28

> 本文件已由“仅挡护”修订为“道路、管网、挡护三专业 CAD 工程量计算”。最新的仓库隔断和建设决策见 [三专业算量与仓库隔断 BDR](./三专业算量与仓库隔断-BDR-v0.3.md)。

## Idea / real task

把 `sayelf-cq-municipal-cad-qto` 固定为重庆市政施工图 CAD 工程量计算工具。核心工作是：单选/多选 DXF 文件录入、项目内检查、标准化、道路/管网/挡护工程量计算、证据留存、作业读取和人工复核。造价人员使用结果草稿进行核对，不把无依据的识别结果直接当作结算事实。

## Step 0 decision

**Improve**：复用已有 DXF 解析、标准化、证据和审核能力，扩展道路与管网确定性规则；不引入第二个项目管理系统，不把 `sayelf-municipal-cost-loop` 接入本仓库，不恢复岗位成果闭环功能。

## Measurable improvement or differentiator

- WebUI 首屏围绕 `Open → Input → Execute → Result → Review`，文件入口支持单选和多选；
- 计算核心只保留道路、管网、挡护三类市政造价算量；
- 多文件检查逐文件返回结果，多专业综合算量保留每个专业的规则包和明细；
- 所有结果固定显示源图哈希、标准化图哈希、规则版本、公式、告警和审核状态；
- 两个仓库无代码、数据、目录、身份、作业、报告或 API 共享。

## Success measure and required evidence

1. `municipal_qto_capabilities` 返回三类专业、三套规则包、文件入口和审核门；
2. 单文件与多文件上传/检查通过本地 HTTP 测试，路径和扩展名受到限制；
3. 合成 DXF 可以提交道路、管网、挡护任意一种或多种参数并生成综合作业；
4. 所有计算结果为 `Inference / REVIEW_REQUIRED`，审核门仍要求五项清单；
5. 原生回归、Python/JavaScript 语法检查和本地 HTTP 冒烟通过；
6. 页面与文档不再把本仓库误写成岗位成果闭环或仅挡护工具。

## Minimum Core

`cad_qto.dxf` → `canonical` → `recognition` → `road / network / retaining` → `job` → `review`。

## Plugin boundaries

`plugins/municipal-cad-qto` 只做 MCP STDIO/Streamable HTTP 和跨宿主配置适配，调用同一份 `cad_qto`，不复制计算逻辑。`municipal_qto_calculate` 是三专业统一入口，旧的 `municipal_qto_calculate_retaining` 仅作为兼容入口。

## Local-first boundary

原始 DXF 上传文件、标准化 DXF、作业 JSON 和审核记录留在项目私有根目录的 `data/cad_inputs/` 与 `data/cad_jobs/`。服务只接受项目根目录内相对路径，默认只监听本机；不上传真实图纸或造价文件。

## Data classification and release

- `Public`：代码、合成 DXF、规则说明、插件契约和脱敏文档；逐项审查后可发布；
- `Sensitive/Restricted`：真实施工图、合同、清单、计价文件、现场照片、项目身份和审核数据；只留在本地；
- `Unknown`：未分类文件不提交、不推送。

GitHub 只发布本次审查后的公开代码、合成样例和文档；不发布 `data/`、真实图纸、密钥、运行日志或项目业务数据。

## State and evidence

作业状态：`PARSED → NORMALIZED → CALCULATED → REVIEW_REQUIRED → REVIEWED_PENDING_AUTHORITY / FACT_CONFIRMED / RETURNED / REJECTED`。源图哈希、标准化图哈希、规则版本、未支持实体、单位异常、关键尺寸缺失或数量告警变化时，必须重新复核。

`Observation` 是 DXF 实体、图层、文字和哈希；`Hypothesis` 是专业候选；`Inference` 是基于人工确认参数的计算数量；`Fact` 只在审核清单和本地身份核验完成后成立。

## WebUI decision

**Required**：造价人员需要同时查看批量文件、图纸检查、专业参数、工程量、公式、哈希、告警和审核门；纯 CLI 不足以支持高效核对。实现采用 Python 标准库本地 HTTP 服务 + 原生 HTML/CSS/JavaScript，不引入前端框架、云模型或通用 CAD 渲染器。

## Explicitly not building

岗位成果管理、钉钉登录、项目成员管理、周报/月报、现场照片账本、通用 ERP、自动套定额/单价、自动审批、自动入账、OCR/视觉识别和通用 DWG/PDF/BIM 解析器。
