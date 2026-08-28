# 跨平台 AI 插件接入与验收 v0.1

## 1. 交付结论

当前交付物已经形成一个可本地运行的跨宿主 MCP 插件包：

- 插件目录：`plugins/municipal-cad-qto/`；
- Codex 插件清单：`.codex-plugin/plugin.json`；
- Claude Code 插件清单：`.claude-plugin/plugin.json`；
- WorkBuddy/CodeBuddy 插件清单：`.codebuddy-plugin/plugin.json`；
- 本地 STDIO MCP：`mcp_server.py`；
- 受控远程 MCP：`mcp_http_server.py`；
- 统一技能说明：`skills/municipal-qto/SKILL.md`；
- Codex、Claude Code、WorkBuddy、百炼、扣子配置模板：`adapters/`。

插件只复用项目内唯一的 `cad_qto` 核心，不复制第二套规则。部署时必须把 `MUNICIPAL_QTO_PROJECT_ROOT` 指向包含 `cad_qto/`、`data/` 和项目图纸的私有根目录。

## 2. 七个统一工具

| 工具 | 作用 | 写入 | 人工门禁 |
|---|---|---:|---:|
| `municipal_qto_capabilities` | 读取能力、规则版本和数据边界 | 否 | 否 |
| `municipal_qto_inspect_dxf` | 检查实体、图层、文字、单位和告警 | 否 | 识别结果为 Hypothesis |
| `municipal_qto_normalize_dxf` | 生成标准化 DXF 副本 | 是 | 不覆盖原图 |
| `municipal_qto_calculate_retaining` | 计算挡护结构工程量草稿 | 是 | 断面参数必须人工确认 |
| `municipal_qto_list_jobs` | 列出本地作业摘要 | 否 | 否 |
| `municipal_qto_get_job` | 读取公式、输入、哈希、告警和审核状态 | 否 | 结果仍是 Inference |
| `municipal_qto_review_job` | 写入人工复核清单和决定 | 是 | 未认证身份不能提升为 Fact |

固定调用顺序：

```text
capabilities → inspect_dxf → normalize_dxf（可选）
→ 人工确认断面 → calculate_retaining → get_job
```

## 3. 各宿主验收矩阵

| 宿主 | 入口 | 已完成 | 尚需租户侧验收 |
|---|---|---|---|
| Codex | 插件清单或 `adapters/codex.config.toml.example` | 本地 STDIO、握手、工具发现、路径门禁、挡护计算 | 当前 Codex 客户端加载一次 |
| Claude Code | `--plugin-dir` + `.claude-plugin`，必要时使用 `adapters/claude-code.mcp.json` | 清单、Skill、MCP 配置模板 | 真实 Claude Code 会话批准并调用一次 |
| WorkBuddy/CodeBuddy | `.codebuddy-plugin` + 本地连接器，必要时使用 `adapters/workbuddy.mcp.json` | 插件清单、STDIO 配置、权限边界 | 当前企业租户的本地连接器权限测试 |
| 通义千问/百炼 | `adapters/qwen-bailian.mcp.json` | HTTP MCP、Bearer 鉴权、项目根目录门禁 | 私有网络部署、平台导入、超时和撤销测试 |
| 豆包/扣子 | `adapters/doubao-coze.mcp.json` | 既有 MCP 转插件的配置模板 | 私有 MCP 导入、工具参数校验和权限测试 |

平台侧状态必须单独记录为 `待租户验收`，不能因为配置文件存在就标记为已上线。

## 4. 本地验收命令

在项目根目录运行：

```text
python -m unittest discover -s tests -v
python plugins/municipal-cad-qto/mcp_server.py
```

当前证据基线：覆盖插件清单与本地 marketplace、DXF 解析、标准化哈希、挡护结构确定性计算、人工审核状态、MCP STDIO 握手、七工具发现、项目路径越界拒绝、作业本地留痕、HTTP Bearer 鉴权和会话校验；测试数量以当前回归输出为准。

## 5. 可信边界

- 当前输入仅为 ASCII DXF；DWG、PDF、IFC、LandXML 不得直接冒充 DXF。
- 图层和文字识别是 `Hypothesis`；公式结果是 `Inference`；人工审核后才可提升为 `Fact`。
- 真实图纸、合同、照片、人员信息、造价文件只留在项目私有根目录，不上传到公共网络或外部模型。
- HTTP 非本机绑定必须设置 `MUNICIPAL_QTO_HTTP_TOKEN`，生产环境还要放在企业私有网络或受控网关后。
- 服务拒绝项目根目录外路径，不覆盖原图，不自动入账、不自动签证、不自动审批。

## 6. 回退与变更规则

- 本地回退：停用宿主中的 MCP 配置或移除插件目录；项目原始 DXF 和既有作业不被删除。
- 规则回退：固定使用 `cq-municipal-retaining-v0.1`，新规则包必须新增版本并重新跑基线测试。
- 平台回退：先撤销远程 MCP 地址或网关路由，再保留本地 STDIO 方式核验。
- 任何平台导入前，检查插件目录、配置模板、日志和打包物中没有真实项目资料、密钥或内部路径。
