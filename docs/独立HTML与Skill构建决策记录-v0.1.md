# 独立 HTML 与 Skill 构建决策记录 v0.1

## 1. 真实任务

依据八项底座构建原则，为 `sayelf-cq-municipal-cad-qto` 生成可单独交付的 HTML 和 Skill，服务重庆市政 CAD 造价算量；两个交付物必须继续与 `sayelf-municipal-cost-loop` 隔断。

## 2. 现有能力与 Step 0 决策

- 已有能力：`web/index.html`、`web/style.css`、`web/app.js` 提供 WebUI；`server.py` 和 `cad_qto/` 提供本地 API 与确定性计算；`plugins/municipal-cad-qto/` 提供 MCP 接入。
- 生态参考：独立前端通常通过本地 HTTP 服务承载计算；可移植 Skill 通常通过宿主的 MCP 工具契约复用核心。本项目不再复制第二套算量规则。
- 决策分类：`Integrate`。
- 可度量差异：HTML 为单文件并内嵌 CSS/JavaScript，可从 `file://` 打开并只访问 `127.0.0.1:8765`；Skill 为独立目录，明确工具顺序、证据状态、人工复核门和本地数据边界。

## 3. 成功证据

1. `standalone/sayelf-cq-municipal-cad-qto.html` 不依赖仓库内相对 CSS/JavaScript 文件，仍能访问本地 API。
2. `standalone/skills/sayelf-cq-municipal-cad-qto/` 通过 Skill 结构校验，且只编排本仓库的 `municipal_qto_*` 能力。
3. 本地服务对 `Origin: null` 提供最小 CORS 响应，支持从 `file://` 发起的读取、检查、转换和计算请求；不开放任意远程来源。
4. 现有单元测试、Python 编译检查、前端语法检查和独立 HTML 构建检查全部通过。

## 4. 最小核心与插件边界

- 最小核心：文件录入/本地转换、DXF 检查、可选标准化、道路/管网/挡护工程量计算、作业留痕、人工复核和 Excel/PDF 导出。
- HTML：只负责本地人机交互和结果下载，不复制计算公式。
- Skill：只负责跨宿主工作编排和可信边界提示，不复制计算公式、不管理另一仓库。
- API/MCP：继续复用当前 `server.py`、`cad_qto/` 和 `plugins/municipal-cad-qto/`。

## 5. 本地优先与数据边界

- 真实图纸、DWG、PDF、DXF、作业和成果属于 `Sensitive/Restricted`，只保留在本机项目 `data/` 目录。
- 独立 HTML 的默认 API 地址为 `http://127.0.0.1:8765`；本地 `Origin: null` 仅为 `file://` 工作流服务，不接收或上传远程文件。
- GitHub 只发布代码、Skill、单文件前端、合成样例和脱敏文档；不发布真实工程资料、密钥、日志或本机路径。

## 6. 状态、检查与证据标签

工作状态保持：`输入 → 检查 → 参数确认 → 计算 → 结果 → 人工复核 → 导出`。图元、文字、图层和哈希是 `Observation`；专业候选是 `Hypothesis`；依据确认参数和公式得到的数量是 `Inference`；五项复核完成且本地身份核验通过后才可标记 `Fact`。关键尺寸、单位或实体缺失时保留告警，不自动补猜。

## 7. WebUI 决策与最简实现

真实任务需要文件选择、进度、告警、审核和独立下载，因此保留 WebUI，遵循：`打开 → 录入 → 执行 → 结果/下载 → 复核`。普通 WebUI 继续同源运行；独立 HTML 由 `scripts/build_standalone_html.py` 从 `web/` 源文件生成，避免手工维护两份界面。

## 8. 演进、回滚与明确不构建

- 演进：先修改 `web/` 或本地服务，再重新生成独立 HTML；Skill 的工具契约随 MCP 版本更新并重新校验。
- 回滚：删除或替换 `standalone/` 交付物即可恢复到普通 WebUI/MCP；不会删除 `data/` 中的原始文件和作业。
- 明确不构建：不做离线浏览器内算量引擎、不把 ODA 二进制打进仓库、不做扫描 PDF OCR、不推断设计意图、不自动套重庆定额/单价、不并入 `sayelf-municipal-cost-loop`，也不默认推送真实资料到公共网络。
