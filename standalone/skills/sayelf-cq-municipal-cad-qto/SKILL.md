---
name: sayelf-cq-municipal-cad-qto
description: "Use the local Chongqing municipal CAD quantity-takeoff workflow for road, drainage-network, and retaining works when drawings must be inspected, converted, calculated, reviewed, or exported."
---

# 重庆市政 CAD 造价算量

本 Skill 只服务 `sayelf-cq-municipal-cad-qto` 的 CAD 造价算量，不调用、不共享 `sayelf-municipal-cost-loop`。它复用项目 MCP 服务和确定性核心，不在 Skill 内复制算量代码。

## 默认工作路径

按以下顺序完成本地证据链：

1. 调用 `municipal_qto_capabilities`，确认项目身份、输入格式、专业范围、规则版本和本地数据边界。
2. 默认使用 DXF。PDF 或 DWG 必须先调用 `municipal_qto_convert_to_dxf`，记录原图 SHA-256、转换 DXF SHA-256、转换方式和告警。
3. 单张图调用 `municipal_qto_inspect_dxf`，多张图调用 `municipal_qto_inspect_dxf_batch`；检查图层、实体、文字、单位和未支持实体。
4. 只有需要副本时调用 `municipal_qto_normalize_dxf`；不得覆盖原始图纸。
5. 取得人工确认的专业参数后，调用 `municipal_qto_calculate`。参数可包含 `road_sections`、`network_sections`、`retaining_sections` 中的一种或多种。
6. 调用 `municipal_qto_get_job`，核对输入、公式、规则版本、哈希、告警和审核状态。
7. 只有用户明确完成核对并确认后，才调用 `municipal_qto_review_job`；五项检查必须齐全：原图、设计依据、专业参数、单位/规则、工程部位。
8. 需要交付文件时调用 `municipal_qto_export_job`，格式只能是 `xlsx` 或 `pdf`；导出后告知本地成果路径。
9. 复核后再次调用 `municipal_qto_get_job`，报告实际状态，不把待审核结果包装为通过结果。

## 输入和专业边界

- 输入入口支持单选或多选；默认 `.dxf`，也支持 `.pdf`、`.dwg` 的本地转 DXF。
- 当前确定性解析实体为 `LINE`、`LWPOLYLINE`、`TEXT`、`MTEXT`；块、填充、圆、标注等未支持实体必须列入人工复核。
- 道路包括路面、基层、底基层、路基挖填、路缘石、人行道。
- 管网包括管道、沟槽开挖、垫层、占用体积、回填、检查井、雨水口、路面恢复。
- 挡护包括墙身、基础、开挖、回填、泄水孔、反滤层、锚杆/锚索、抗滑桩、喷射混凝土、钢筋网。
- 不猜测设计意图、关键尺寸、单位、重庆定额子目、单价或结算口径；缺少依据就停止并标记缺口。

## 可信状态

- 图层、实体和文字是 `Observation`；专业候选是 `Hypothesis`。
- 依据人工确认参数和版本化公式得到的数量是 `Inference`。
- 只有五项人工复核完成且通过本地身份核验，才可记录为 `Fact`。
- 未安装本地 DWG 转换器、扫描 PDF、路径越界、单位异常或转换告警时，不猜测、不计算假结果。

## 数据边界和宿主接入

- 真实图纸、合同、计价文件、作业和成果属于本地私有数据，只使用项目根目录内相对路径，不上传到外部模型、公共网络或第三方 API。
- 可通过 `municipal_qto_*` MCP 工具接入 Codex、Claude Code、WorkBuddy、千问/百炼和豆包/扣子等支持 MCP 的宿主；宿主只应连接本地 STDIO 或受控私有 MCP。
- 独立 HTML 是本地人机界面，默认连接 `http://127.0.0.1:8765`；普通路径为“打开 → 录入 → 执行 → 结果/下载 → 复核”。
