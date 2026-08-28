# 跨平台 AI 辅助插件构建决策记录

版本：v0.1
日期：2026-08-28
目标平台：Codex、Claude Code、WorkBuddy/CodeBuddy、通义千问/百炼、豆包/扣子

## 1. Idea / real task

让不同 AI 工作台通过统一工具协议调用本地市政图纸算量核心：识别 DXF 几何、生成标准化 DXF、计算道路/管网/挡护工程量草稿、读取作业结果和审核证据。AI 负责发现、编排、解释和提醒；几何规则、哈希、状态、权限和最终事实仍由项目本地系统负责。

## 2. Closest existing projects or capabilities

平台能力与入口已查证：

- [OpenAI Codex MCP](https://developers.openai.com/codex/mcp/)：支持本地 STDIO 和 Streamable HTTP MCP；Codex CLI、桌面端和 IDE 可共享 MCP 配置。
- [Claude Code 插件](https://code.claude.com/docs/en/plugins)：支持 `.claude-plugin/plugin.json`、`skills/`、`.mcp.json`，可用 `--plugin-dir` 本地测试。
- [WorkBuddy 连接器](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Connector)：支持 MCP+CLI、Skill+CLI 和自定义连接器。
- [WorkBuddy 插件系统](https://www.workbuddy.cn/docs/workbuddy/Plugins)：支持 Skill、MCP、Hook、Agent、Rule 插件。
- [百炼自定义 MCP](https://help.aliyun.com/zh/model-studio/custom-mcp)：支持自行开发 MCP，使用脚本部署为 npx/uvx，或通过 http 接入远程 MCP。
- [扣子基于 MCP 创建插件](https://docs.coze.cn/guides_create_a_plugin_based_on_mcp)：支持由已有 MCP 服务创建自定义插件；流式插件另有 SSE 协议要求。

现有本地核心已经具备 DXF 标准化、道路/管网/挡护确定性计算、证据和审核状态；缺口是标准 MCP 工具层、宿主安装适配和跨平台安全说明。

## 3. Step 0 decision

**Integrate**。

理由：算量核心已存在，MCP 是多平台共同接口；本次只增加薄适配层，不复制或重写平台逻辑。Codex/Claude Code/WorkBuddy 首选本地 STDIO；千问/豆包如果只能访问远程服务，必须走经授权的私有部署或脱敏数据模式，不能把真实图纸静默上传到公网。

## 4. Measurable improvement or differentiator

- 一个确定性核心同时被至少三类本地宿主调用，业务逻辑不分叉；
- MCP 工具描述、输入输出和错误行为固定，支持工具清单自动发现；
- 读工具与写工具显式标注只读/幂等/需要确认；
- 任一算量结果继续保留源图哈希、标准化图哈希、规则版本、公式、输入快照和审核状态；
- 未配置项目根目录或检测到项目目录外路径时拒绝执行。

## 5. Success measure and required evidence

1. MCP STDIO 完成 `initialize → tools/list → tools/call` 冒烟测试。
2. 至少验证 `capabilities`、`inspect_dxf`、`inspect_dxf_batch`、`normalize_dxf`、`calculate`、`list_jobs`、`get_job` 七类核心工具。
3. Codex/Claude Code/WorkBuddy 的配置文件可被静态校验，且调用同一份本地核心。
4. 百炼/扣子/豆包提供可复制的接入模板，但在未完成私有部署和数据合规审批前不宣称已完成生产接入。
5. 所有测试使用合成图纸；真实重庆项目需另行做脱敏双算和人工验收。

## 6. Minimum Core

```text
local municipal_qto core
  → stdio MCP server
  → common tool contract
  → host-specific manifest/config/skill
```

MCP 工具：

- `municipal_qto_capabilities`：读取支持范围、规则版本、数据边界；
- `municipal_qto_inspect_dxf`：只读解析实体、图层和告警；
- `municipal_qto_normalize_dxf`：在项目私有目录内生成标准化 DXF；
- `municipal_qto_calculate`：依据人工确认的道路、管网、挡护参数生成综合算量作业；
- `municipal_qto_calculate_retaining`：旧版挡护调用兼容入口；
- `municipal_qto_list_jobs`：列出本项目作业摘要；
- `municipal_qto_get_job`：读取完整作业、公式、证据和审核状态。

## 7. Plugin boundaries

- `cad_qto/`：平台无关的本地规则核心；
- `mcp_server.py`：平台无关的标准 MCP STDIO 适配器；
- `plugins/municipal-cad-qto/`：Codex/Claude Code/WorkBuddy 的插件清单、Skill 和配置；
- `adapters/`：千问/豆包/百炼的接入模板和平台差异说明；
- 不为每个平台复制一份计算逻辑，不把平台 SDK 放进 Core。

## 8. Local-first boundary

本地宿主通过 STDIO 直接读项目私有文件；MCP 服务只接受项目根目录内的相对路径。远程 HTTP/SSE 仅作为经过授权的部署形态，必须使用私有网络、网关鉴权、最小范围数据和审计，不作为本地真实图纸的默认路径。

## 9. Data classification and local trust boundary

- 真实图纸、合同、现场照片、项目账本、人员身份、造价文件和密钥：`Sensitive/Restricted`，只留在项目私有信任边界；
- 合成 DXF、脱敏样例、工具 schema、安装说明：可在逐项审查后标记 `Public`；
- MCP 工具只返回必要的结构化结果和私有路径标签，不返回密钥，不把本地文件内容转发给模型之外的服务。

## 10. GitHub/public release decision

当前：**Blocked**。

原因：工作区无可确认的 Git 发布审查记录，且真实数据分类尚未逐项复核。未来只有代码、合成样例、脱敏文档和明确公开资料可以发布；真实 `data/`、配置密钥、项目人员、图纸和运行日志必须排除并完成 staged diff 泄露检查。

## 11. External transfer plan

默认无外部传输。若后续用户明确授权将脱敏工具服务部署到百炼/扣子/豆包：

1. 先本地脱敏和最小化；
2. 确认目标、访问控制、保留周期和审计方式；
3. 使用 HTTPS/SSE/Streamable HTTP 和服务级鉴权；
4. 做输出泄露检查和可撤销测试；
5. 保留本地模式作为回退。

## 12. State, change signals, and next-check rule

工具状态：`AVAILABLE → RUNNING → REVIEW_REQUIRED → APPROVED`，错误状态为 `BLOCKED`。

下一次检查由以下信号触发：源图 SHA 变化、规则包变化、插件清单变化、MCP 工具 schema 变化、宿主版本变化、未支持实体出现、跨目录路径、单位异常或作业结果告警。无变化的作业不轮询；重要状态变化时立即通知或由宿主下一次调用读取。

## 13. Observation / inference / hypothesis / fact boundary

- `Observation`：MCP 返回的实体、图层、文本、哈希和人工输入；
- `Inference`：公式推导的数量和汇总；
- `Hypothesis`：图层/文字产生的构件候选和缺证提醒；
- `Fact`：人工完成图纸、断面、规则和数量复核后确认的造价事实。

## 14. Evolution, validation, canary, version, rollback

工具 schema、解析器、规则包和插件包都带版本号。升级流程为 `Observe → Challenge → Validate → Canary → Promote`；先跑合成回归，再跑真实脱敏双算，差异超阈值则保留旧版本。作业输出保留输入快照和结果快照，回滚切换版本，不删除原始资料。

## 15. WebUI decision

WebUI 已存在且有必要：审核人员需要看到图层候选、公式、告警、哈希和状态。MCP 工具本身不复制 WebUI，只输出结构化证据；普通路径保持 `打开 → 输入 → 执行 → 结果`。

## 16. Simplest reliable implementation

Python 标准库 JSON-RPC/MCP STDIO 适配器 + 现有 `cad_qto` 核心 + 三套本地插件清单 + 千问/豆包远程接入模板。暂不引入 MCP SDK、云 SDK 或模型 SDK，减少依赖和数据外传面。

## 17. Explicitly not building

- 不为 Codex、Claude Code、WorkBuddy、千问、豆包分别重写业务核心；
- 不自动上传真实图纸到百炼、扣子或任何公共网络；
- 不承诺平台市场上架、OAuth 或企业审批已完成；
- 不用平台模型替代几何规则和人工审核；
- 不自动发布真实项目数据或未审查文件到公共 GitHub；目标仓库已由维护者创建，所有公开发布内容仍须先通过数据分类、泄漏扫描和人工复核。
