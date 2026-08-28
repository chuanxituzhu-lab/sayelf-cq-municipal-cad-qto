# 重庆市政 CAD 算量插件

本插件把项目内的 `cad_qto` 确定性算量核心包装为标准 MCP 工具，供 Codex、Claude Code、WorkBuddy/CodeBuddy 及支持 MCP 的通义千问/百炼、豆包/扣子使用。

所属核心仓库名：`sayelf-cq-municipal-cad-qto`。本目录仍使用稳定插件 ID `municipal-cad-qto`，Python 核心包仍使用 `cad_qto`；三者不是同一层级的名称，不要在宿主配置中互相替换。

完整的“一个项目部、一套数据”部署和日常使用步骤见项目根目录 [README.md](../../README.md) 的“单个项目部部署与使用手册”章节；本文件专门说明 AI 宿主插件接入。

本插件所在项目当前仓库为 [`sayelf-municipal-cost-loop`](https://github.com/chuanxituzhu-lab/sayelf-municipal-cost-loop)；插件自身继续使用 `municipal-cad-qto` 作为兼容标识。

## 能做什么

- 检查项目内 ASCII DXF 的图层、实体、文字、单位和不支持实体；
- 生成不覆盖原图的标准化 DXF；
- 按人工确认的挡护结构断面计算墙身、基础、开挖、回填、泄水孔、反滤层、锚杆、抗滑桩、喷射混凝土和钢筋网；
- 保存源图哈希、标准化图哈希、规则版本、公式、输入快照、告警和人工审核状态；
- 读取项目内算量作业，供 AI 汇总和提醒。
- 记录人工复核清单、审核决定和复核历史；没有本地已认证审核身份时不会提升为 `Fact`。

## 本地安装/测试

插件根目录是本目录。项目根目录默认按当前仓库结构解析；如插件被复制到其他位置，设置 `MUNICIPAL_QTO_PROJECT_ROOT` 指向包含 `cad_qto/`、`fixtures/` 和 `data/` 的项目根目录。

这里的插件是“宿主适配层 + 项目唯一算量核心”，不是把核心复制成第二份。单独复制本目录而不提供 `cad_qto/` 和私有项目数据根目录，服务会故意启动失败，避免出现看似可用但规则版本不一致的结果。

Codex、Claude Code 和 WorkBuddy 优先使用本地 STDIO MCP。根目录 `.mcp.json` 是 Codex Agent Plugins v1 清单，使用 `${PLUGIN_ROOT}`；Claude Code 使用其专用变量 `${CLAUDE_PLUGIN_ROOT}`，不要把两套变量混用。对应配置模板在 `adapters/`：

- Codex 插件安装：直接把本目录作为插件目录；项目级直接配置：`adapters/codex.config.toml.example`；
- Claude Code：`adapters/claude-code.mcp.json`；
- WorkBuddy：`adapters/workbuddy.mcp.json`。

Codex 的项目根目录通过 `MUNICIPAL_QTO_PROJECT_ROOT` 指定；Claude/WorkBuddy 也必须把该变量指向同一个项目根目录。插件不会替用户写入全局配置、创建账号或复制项目数据。

启动 MCP 服务后，宿主应能发现以下工具：

```text
municipal_qto_capabilities
municipal_qto_inspect_dxf
municipal_qto_normalize_dxf
municipal_qto_calculate_retaining
municipal_qto_list_jobs
municipal_qto_get_job
municipal_qto_review_job
```

在项目根目录执行本地冒烟测试：

```text
python -m unittest discover -s tests -v
python plugins/municipal-cad-qto/mcp_server.py
```

## 千问/百炼、豆包/扣子

这类云端平台通常需要配置远程 MCP 地址。插件提供 `mcp_http_server.py` 和配置模板，但不替用户部署公网服务：

```text
python plugins/municipal-cad-qto/mcp_http_server.py
```

默认只监听 `127.0.0.1:8787`。绑定非本机地址时必须设置 `MUNICIPAL_QTO_HTTP_TOKEN`；生产环境还应置于企业私有网络或受控网关之后，并完成访问控制、保留周期、审计和脱敏审批。

远程平台调用的是私有部署中的相对路径，不能读取调用方电脑的本地文件；真实图纸不得因为“插件兼容”而上传到公共网络。千问/百炼参考 `adapters/qwen-bailian.mcp.json`，豆包/扣子参考 `adapters/doubao-coze.mcp.json`。

当前输入边界仍是 ASCII DXF。DWG、PDF、IFC、LandXML 的转换属于部署侧的本地预处理能力，尚未在本插件内伪装成“自动识别”；转换后必须重新执行 `municipal_qto_inspect_dxf` 并保留源文件哈希。

## 结果口径

图层/文字识别是 `Hypothesis`，公式计算是 `Inference`，结果固定为 `REVIEW_REQUIRED / 待人工审核`。只有生产、技术和造价审核后才可成为 `Fact`，本插件不自动入账、不自动签证、不自动审批。
