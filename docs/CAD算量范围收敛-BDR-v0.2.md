# sayelf-cq-municipal-cad-qto：CAD 造价算量范围收敛决策

版本：v0.2
日期：2026-08-28

## Idea / real task

把 `sayelf-cq-municipal-cad-qto` 收敛为重庆市政施工图 CAD 工程量计算工具。核心工作是：项目内 DXF 检查、标准化、挡护结构工程量计算、证据留存、作业读取和人工复核。造价人员使用结果草稿进行核对，不把无依据的识别结果直接当作结算事实。

## Closest existing projects or capabilities

- 工作区已有 `cad_qto` 确定性核心和 `municipal-cad-qto` MCP 插件，直接复用；
- [OpenConstructionERP 的 Quantity Takeoff](https://github.com/datadrivenconstruction/OpenConstructionERP/blob/main/docs/user-guide/quantity-takeoff.md) 说明了图纸到可审计工程量的通用方向；
- [OpenTakeoff](https://github.com/HexNinja555/opentakeoff) 提供浏览器端 takeoff 与 MCP 的参考；
- [fabrication-bom-api](https://github.com/nepdesk/fabrication-bom-api) 提供 DXF/DWG 到结构化清单的参考，但许可证和业务范围不适合直接并入当前核心。

当前仓库的实际差异是：本地优先、只接受项目目录内相对路径、以重庆市政挡护结构规则包计算、保留源图/标准化图哈希并强制人工复核。

## Step 0 decision

**Improve**：不重写 CAD 核心，不接入第二套项目管理系统；删除无关的岗位成果闭环、钉钉、项目成员、周报/月报和通用连接器代码，重建 CAD 造价算量专用服务与 WebUI。

## Measurable improvement or differentiator

- WebUI 首屏只围绕 `Open → Input → Execute → Result → Review`；
- 服务端只保留 CAD 能力路由，删除岗位成果、项目成员、报告和身份系统路由；
- 不新增前端依赖；
- 结果固定显示源图哈希、标准化图哈希、规则版本、公式、告警和审核状态；
- 通过 `rg` 检查主代码和主页面不再出现“岗位成果闭环/周报/钉钉/项目成员”等非 CAD 业务入口。

## Success measure and required evidence

1. `municipal_qto_capabilities` 返回 CAD 输入、规则包、审核门和禁止外传边界；
2. 合成 DXF 可完成检查、标准化、挡护结构计算和作业读取；
3. 所有计算结果为 `Inference / REVIEW_REQUIRED`，审核门仍要求五项清单；
4. 原生 `unittest`、Python/JavaScript 语法检查和本地 HTTP 冒烟全部通过；
5. 浏览器页面标题和内容为“重庆市政 CAD 工程量计算（造价算量）”，不再出现岗位成果闭环。

## Minimum Core

`cad_qto.dxf` → `canonical` → `recognition` → `retaining` → `job` → `review`。

## Plugin boundaries

`plugins/municipal-cad-qto` 只做 MCP STDIO/Streamable HTTP 和跨宿主配置适配，调用同一份 `cad_qto`，不复制计算逻辑。

## Local-first boundary

原始 DXF、标准化 DXF、作业 JSON 和审核记录留在项目私有根目录的 `data/cad_jobs/`。服务只接受项目根目录内相对路径，默认只监听本机；不上传真实图纸或造价文件。

## Data classification and local trust boundary

- `Public`：代码、合成 DXF、规则说明、插件契约和脱敏文档；逐项审查后可发布；
- `Sensitive/Restricted`：真实施工图、合同、清单、计价文件、现场照片、项目身份和审核数据；只留在本地；
- `Unknown`：未分类文件不提交、不推送。

## GitHub/public release decision: Allowed — review evidence

仅发布本次 staged diff 中的 CAD 代码、合成样例和文档；不发布 `data/`、真实图纸、密钥、运行日志或项目业务数据。推送前检查 staged diff、未跟踪文件和文件类型。
## External transfer plan

本次只更新用户指定的 GitHub 仓库中的公开代码和文档；不向外部模型、第三方 API 或远程存储上传项目文件。

## State, change signals, and next-check rule

作业状态：`PARSED → NORMALIZED → CALCULATED → REVIEW_REQUIRED → REVIEWED_PENDING_AUTHORITY / FACT_CONFIRMED / RETURNED / REJECTED`。源图哈希、标准化图哈希、规则版本、未支持实体、单位异常、关键尺寸缺失或数量告警变化时，必须重新复核。

## Observation / inference / hypothesis / fact boundary

- `Observation`：DXF 实体、图层、文字、哈希和人工确认断面；
- `Hypothesis`：图层/文字产生的构件候选；
- `Inference`：根据已确认输入和版本化公式推导的数量；
- `Fact`：通过本地已认证审核后可进入正式造价流程的结果。

## Evolution, validation, canary, version, and rollback plan

先跑合成样例和回归测试，再进入真实脱敏双算；规则包和插件版本显式记录。若新 UI 或服务不通过验证，回滚本次提交即可，不删除原始私有数据。

## WebUI decision: Required — reason

造价人员需要同时查看图纸检查结果、识别候选、断面输入、工程量、公式、哈希、告警和审核门；纯 CLI 不足以支持高效核对。

## Default WebUI path

`Open → Input → Execute → Result → Review`

## Simplest reliable implementation

Python 标准库本地 HTTP 服务 + 原生 HTML/CSS/JavaScript + 现有 `cad_qto` 和 MCP 插件；不引入前端框架、数据库、云模型或通用 CAD 渲染器。

## Explicitly not building

岗位成果管理、钉钉登录、项目成员管理、周报/月报、现场照片账本、通用 ERP、自动套定额/单价、自动审批、自动入账、OCR/视觉识别和通用 DWG/PDF/BIM 解析器。
