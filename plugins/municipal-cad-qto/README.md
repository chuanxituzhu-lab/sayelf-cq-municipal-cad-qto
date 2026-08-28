# 重庆市政 CAD 造价算量插件

本插件把项目内 `cad_qto` 确定性核心包装为标准 MCP 工具，供 Codex、Claude Code、WorkBuddy/CodeBuddy 及支持 MCP 的千问/百炼、豆包/扣子私有部署调用。

## 边界

插件是宿主适配层，不是第二份算量核心。所有平台调用同一份 `cad_qto`，只接受项目根目录内相对路径；真实图纸、合同、计价文件和审核数据留在本仓库的本地私有目录。本插件不导入、不调用、不共享 `sayelf-municipal-cost-loop` 的代码、数据、项目目录、身份、作业、报告或 API。

## 工具

```text
municipal_qto_capabilities
municipal_qto_convert_to_dxf
municipal_qto_inspect_dxf
municipal_qto_inspect_dxf_batch
municipal_qto_normalize_dxf
municipal_qto_calculate
municipal_qto_calculate_retaining       # 旧调用兼容入口
municipal_qto_list_jobs
municipal_qto_get_job
municipal_qto_review_job
municipal_qto_export_job
```

推荐调用顺序：

```text
capabilities
  → convert_to_dxf（PDF/DWG 可选）
  → inspect_dxf / inspect_dxf_batch
  → normalize_dxf（可选）
  → 人工确认道路 / 管网 / 挡护参数
  → calculate
  → get_job
  → review_job
  → export_job（Excel / PDF）
```

文件可以在 WebUI 通过单选/多选录入；默认 DXF，PDF 由本机 PyMuPDF 提取矢量图元后生成 DXF，DWG 依赖部署机已安装并配置的 ODA File Converter。MCP 调用仍必须传项目根目录内的相对路径，批量检查使用 `municipal_qto_inspect_dxf_batch`。不同文件不混成一个算量作业。

## 当前支持

- 输入：ASCII DXF（默认）；PDF（本地矢量转 DXF）；DWG（本机转换器转 DXF）；
- 实体：`LINE`、`LWPOLYLINE`、`TEXT`、`MTEXT`；
- 道路：面层、基层、底基层、挖方、填方、路缘石、侧平石/人行道；
- 管网：管道、沟槽开挖、垫层、回填、检查井、雨水口、道路恢复；
- 挡护：墙身、基础、开挖、回填、泄水孔、反滤层、锚杆/锚索、抗滑桩、喷射混凝土、钢筋网；
- 规则包：`cq-municipal-road-v0.1`、`cq-municipal-network-v0.1`、`cq-municipal-retaining-v0.1`；
- 输出：数量、单位、公式、输入快照、专业、规则包版本、源图/标准化图 SHA-256、转换双哈希、告警和审核状态；作业可独立导出 Excel 或 PDF。

图层/文字识别是 `Hypothesis`，公式计算是 `Inference`。只有完成五项人工检查并通过本地身份核验，结果才可成为 `Fact`。插件不自动套定额、不自动审批、不自动入账。

## 配置

设置 `MUNICIPAL_QTO_PROJECT_ROOT` 指向包含 `cad_qto/`、`fixtures/` 和 `data/` 的项目根目录。默认使用本地 STDIO MCP：

```text
python plugins/municipal-cad-qto/mcp_server.py
```

受控私有网络可使用 Streamable HTTP：

```text
python plugins/municipal-cad-qto/mcp_http_server.py
```

默认只监听 `127.0.0.1:8787`；绑定非本机地址时必须设置 `MUNICIPAL_QTO_HTTP_TOKEN`，并由私有网络或受控网关保护。

## 数据边界

WebUI 上传的 DXF/PDF/DWG 与本地转换副本写入本仓库 `data/cad_inputs/`，作业写入 `data/cad_jobs/`，导出文件写入 `data/cad_exports/`，均不进入 GitHub。真实图纸、合同、计价文件和作业数据不得上传给外部模型或公共网络。公开发布前只允许代码、合成样例、插件契约和脱敏文档通过检查。

## 格式边界

PDF/DWG 只在本地通过 `municipal_qto_convert_to_dxf` 进入插件；扫描 PDF 不自动 OCR，未安装 DWG 转换器时返回失败并保留原因。转换必须保留原文件哈希，生成 DXF 后重新执行 `municipal_qto_inspect_dxf`。IFC、LandXML 仍不属于当前输入。
