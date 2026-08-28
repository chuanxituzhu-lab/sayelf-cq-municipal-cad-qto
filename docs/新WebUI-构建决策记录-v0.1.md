# 新 WebUI 构建决策记录

版本：v0.1
日期：2026-08-28
范围：市政工程岗位成果闭环演示项目本地 WebUI

## 1. Idea / real task

重建本地 WebUI，使它准确表达“市政工程岗位成果闭环演示项目”，让项目经理、生产、技术和造价岗位围绕同一项目状态工作；在不改变核心规则和 API 契约的前提下，把 CAD 挡护结构算量纳入可审核的工作面。

## 2. Step 0 现有能力与缺口

已查阅当前工作区、指定 GitHub 仓库和开源方案。可复用的最近能力包括：

- 当前项目已有 `cad_qto`、`server.py`、本地数据账本和跨平台 MCP 插件；
- [OpenCADStudio](https://github.com/HakanSeven12/OpenCADStudio) 提供开源浏览器 CAD 能力，可作为未来图形查看器参考；
- [ezdxf](https://github.com/mozman/ezdxf) 是成熟的 DXF 读写库，可作为未来实体扩展参考；
- [OpenConstructionERP](https://openconstructionerp.com/?lang=en) 覆盖更宽的施工管理方向，但不替代本项目的本地、证据约束和重庆挡护结构规则闭环。

缺口不是再造 CAD 或 ERP，而是现有界面没有把岗位成果闭环作为主叙事，首屏、状态、审核证据和 CAD 结果之间的关系不够清楚。

## 3. Decision

**Improve**：在已有本地 API 和确定性核心之上重建一个更贴合岗位成果闭环的 WebUI，不新增业务核心、不新增外部依赖、不复制工程量公式。

## 4. Measurable difference

- 首屏直接显示完整项目身份、当前岗位、闭环状态和下一步动作；
- 项目总览到岗位成果/CAD 算量最多一次导航操作；
- CAD 结果区固定显示 `Observation / Hypothesis / Inference / Fact` 边界、规则版本、哈希、告警和审核状态；
- 新 UI 通过后才删除旧 `web/` 内容，服务器入口和 API 保持兼容；
- 用现有合成 DXF、API 冒烟、浏览器 DOM 检查和回归测试形成证据。

## 5. Minimum Core and plugin boundary

- 最小 Core：现有 `cad_qto` + `server.py` API + 项目本地 `data/`。
- WebUI：只负责导航、输入、状态可视化、结果展示和人工操作确认。
- 插件：继续通过 MCP 调用相同核心；本次不把浏览器逻辑复制进 Codex、Claude Code、WorkBuddy 适配层。

## 6. WebUI decision and simplest implementation

需要 WebUI，因为实际岗位工作必须可见地完成“打开 → 输入 → 执行 → 结果 → 审核”。采用原生 HTML/CSS/JavaScript，保留当前 Python 标准库服务，不引入构建工具、前端框架或云端依赖。界面采用渐进披露：先看项目状态，再展开证据、公式和人工审核信息。

## 7. Local-first, data classification and public release

- UI、服务和算量均在本机执行；项目私有文件只接受项目目录内相对路径。
- 真实图纸、照片、合同、账本、身份和密钥为 `Sensitive/Restricted`，不能进入提交、提交记录或 GitHub。
- 新增代码、合成样例和本决策文档可按 `Public` 候选处理，但推送前必须审查 staged diff、未跟踪文件和发布包。
- 未分类或疑似运行数据一律留在本地；`data/` 继续被 `.gitignore` 排除。

## 8. State, evidence and next-check rule

UI 不改变状态机，只展示服务端返回的状态。源图哈希、标准化图哈希、规则版本变化，或实体/单位/数量告警出现时，页面必须明确提示“待人工复核”。下一次真实验收仍是脱敏重庆项目 DXF 与人工底稿双算；在此之前不宣称生产级全自动算量。

## 9. Evolution and rollback

先在临时 `web_next/` 目录实现并验证；验证成功后以版本化文件替换旧 `web/`，保留 Git 历史作为回滚点。若 UI 验收失败，只回滚 WebUI 文件，不回滚核心、插件、项目数据或审核记录。

## 10. Explicitly not being built

- 不新增通用 CAD 渲染器、OCR、模型调用或数据库；
- 不改变现有 API、状态机、规则版本和审核门槛；
- 不自动审批、不自动入账、不自动把识别候选升级为事实；
- 不删除 `cad_qto`、`server.py`、插件、测试、文档或项目私有数据。
