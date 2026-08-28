# 跨平台接入说明

| 宿主 | 当前接入方式 | 当前状态 | 关键边界 |
|---|---|---|---|
| Codex | 本地 STDIO MCP，或 Codex 插件清单 | 可本地测试 | `MUNICIPAL_QTO_PROJECT_ROOT` 必须指向项目根目录 |
| Claude Code | `.claude-plugin` + `.mcp.json` + Skill | 可本地测试 | 通过 `--plugin-dir` 加载并按提示批准 MCP |
| WorkBuddy/CodeBuddy | 自定义连接器/插件 + 本地 STDIO MCP | 可按企业版本测试 | 通过连接器页面安装，确认本地路径与权限 |
| 通义千问/百炼 | 自定义 MCP 的 stdio/uvx/http 部署或私有网关 | 提供模板，需平台侧部署验收 | 云端不能直接读取用户本地文件 |
| 豆包/扣子 | 基于已有 MCP 服务创建插件 | 提供模板，需平台侧导入验收 | 仅允许经过授权的私有 MCP 地址 |

## 配置文件的边界

根目录 `.mcp.json` 遵循 Codex Agent Plugins v1，使用 `${PLUGIN_ROOT}`；Claude Code 必须使用 `claude-code.mcp.json` 中的 `${CLAUDE_PLUGIN_ROOT}`。`codex.config.toml.example` 是 Codex 项目级直接配置示例，不是 Claude 或云端平台的配置文件。所有宿主都应通过 `MUNICIPAL_QTO_PROJECT_ROOT` 指向同一项目根目录，避免每个平台各自生成一套数据。

## 本地宿主

使用 `mcp_server.py`。首个调用顺序固定为：

```text
capabilities → inspect_dxf / inspect_dxf_batch → normalize_dxf（可选）
→ 人工确认道路 / 管网 / 挡护参数 → calculate → get_job
```

### Codex 本地插件

项目根目录已经提供 `.agents/plugins/marketplace.json`。在项目根目录执行以下两步即可把本地插件加入 Codex 的插件目录并安装；这会修改当前用户的 Codex 插件配置，但不会上传项目数据：

```text
codex plugin marketplace add .
codex plugin add municipal-cad-qto@municipal-project
```

安装后，仍需在宿主环境设置 `MUNICIPAL_QTO_PROJECT_ROOT` 为本项目根目录。也可以不安装插件，直接按 `codex.config.toml.example` 做项目级 MCP 配置。

## 远程宿主

使用 `mcp_http_server.py`，其 `/mcp` 接收 MCP JSON-RPC POST，其 `/healthz` 只做健康检查。生产部署前必须：

1. 使用企业私有网络、反向代理或受控网关；
2. 设置服务级 Bearer Token，并限制来源；
3. 将 `MUNICIPAL_QTO_PROJECT_ROOT` 指向私有项目存储；
4. 禁止把真实图纸作为工具参数或日志上传；
5. 完成平台侧工具测试、权限测试、超时测试和撤销测试。

百炼支持自定义 MCP 的脚本部署或 http 接入；扣子支持由已有 MCP 创建插件。不同平台的具体控制台字段和审核结果必须以当前租户页面为准，不能把模板视为已完成上线。
