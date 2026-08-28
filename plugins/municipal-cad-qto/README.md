# 重庆市政 CAD 造价算量插件

本插件把项目内 `cad_qto` 确定性核心包装为标准 MCP 工具，供 Codex、Claude Code、WorkBuddy/CodeBuddy 及支持 MCP 的千问/百炼、豆包/扣子私有部署调用。

## 边界

插件是宿主适配层，不是第二份算量核心。所有平台调用同一份 `cad_qto`，只接受项目根目录内相对路径；真实图纸、合同、计价文件和审核数据留在本地私有目录。

## 工具

```text
municipal_qto_capabilities
municipal_qto_inspect_dxf
municipal_qto_normalize_dxf
municipal_qto_calculate_retaining
municipal_qto_list_jobs
municipal_qto_get_job
municipal_qto_review_job
```

调用顺序：

```text
capabilities → inspect_dxf → normalize_dxf（可选）
→ 人工确认挡护断面 → calculate_retaining → get_job → review_job
```

## 当前支持

- 输入：ASCII DXF；
- 实体：`LINE`、`LWPOLYLINE`、`TEXT`、`MTEXT`；
- 规则包：`cq-municipal-retaining-v0.1`；
- 挡护结构：墙身、基础、开挖、回填、泄水孔、反滤层、锚杆/锚索、抗滑桩、喷射混凝土、钢筋网；
- 输出：数量、单位、公式、输入快照、源图/标准化图 SHA-256、告警和审核状态。

图层/文字识别是 `Hypothesis`，公式计算是 `Inference`。只有完成五项人工检查并通过本地身份核验，结果才可成为 `Fact`。插件不自动套定额、不自动审批、不自动入账。

## 配置

设置 `MUNICIPAL_QTO_PROJECT_ROOT` 指向包含 `cad_qto/`、`fixtures/` 和 `data/` 的项目根目录。默认使用本地 STDIO MCP：

```text
python plugins/municipal-cad-qto/mcp_server.py
```

远程 Streamable HTTP 仅用于经授权的私有部署：

```text
python plugins/municipal-cad-qto/mcp_http_server.py
```

默认只监听 `127.0.0.1:8787`；绑定非本机地址时必须设置 `MUNICIPAL_QTO_HTTP_TOKEN`，并由私有网络或受控网关保护。

## 格式边界

DWG、PDF、IFC、LandXML 不是当前插件的输入。若部署侧在本地完成转换，必须保留原文件哈希，生成 DXF 后重新执行 `municipal_qto_inspect_dxf`；不把转换能力伪装成插件内自动识别。
