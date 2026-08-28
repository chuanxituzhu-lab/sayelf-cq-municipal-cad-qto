---
name: municipal-qto
description: Use the local municipal CAD quantity-takeoff tools for Chongqing road, drainage networks and retaining structures. Apply when the user asks to inspect DXF drawings, normalize CAD files, calculate road/network/retaining quantities, explain formulas, or prepare review evidence.
---

# 重庆市政 CAD 工程量辅助

本技能只服务 `sayelf-cq-municipal-cad-qto` 的 CAD 造价算量，不调用或共享 `sayelf-municipal-cost-loop`。

使用本技能时遵循以下顺序：

1. 先调用 `municipal_qto_capabilities`，确认当前宿主、输入格式、道路/管网/挡护专业、规则版本和数据边界。
2. 默认使用 DXF；若输入为 PDF 或 DWG，先调用 `municipal_qto_convert_to_dxf`，确认本地转换状态、原始 SHA-256、转换 SHA-256 和告警，再对生成的 DXF 检查。
3. 对单张 DXF 调用 `municipal_qto_inspect_dxf`；对多张 DXF 调用 `municipal_qto_inspect_dxf_batch`，检查图层、实体、文字和未支持实体。
4. 只有在需要生成副本时调用 `municipal_qto_normalize_dxf`；不得覆盖原始图纸。
5. 只有取得人工确认的专业参数后，才调用 `municipal_qto_calculate`；参数数组可包含 `road_sections`、`network_sections`、`retaining_sections` 中的一种或多种。
6. 计算后调用 `municipal_qto_get_job`，完整展示专业、公式、输入、SHA-256、规则版本、告警和审核状态。
7. 旧调用若只有挡护参数，可暂时使用 `municipal_qto_calculate_retaining`；新集成统一使用 `municipal_qto_calculate`。
8. 只有用户明确完成核对并确认后，才调用 `municipal_qto_review_job`；通过前必须勾选原图、设计依据、专业参数、单位/规则和工程部位五项。
9. 需要交付文件时调用 `municipal_qto_export_job`，格式只能是 `xlsx` 或 `pdf`，并把本地成果路径告知用户。
10. 复核后再次调用 `municipal_qto_get_job`，报告实际状态：`REVIEWED_PENDING_AUTHORITY`、`FACT_CONFIRMED`、`RETURNED` 或 `REJECTED`。
11. 最终回答必须说明：识别结果是 `Hypothesis`、计算结果是 `Inference`；未通过本地身份核验的审核不得作为 `Fact`。

安全约束：

- 只使用项目私有根目录内的相对路径；路径越界、公开 URL、非 DXF/PDF/DWG 输入或缺少关键尺寸时停止并说明原因。扫描 PDF 和未安装转换器的 DWG 不得猜测。
- 不猜测设计意图、地质参数、重庆定额子目、单价或结算口径。
- 不上传真实图纸、合同、照片、人员信息或造价文件到外部模型、公共网络或第三方 API。
- 发现未支持实体、单位异常、图层语义不唯一或规则版本变化时，把问题列为人工复核项。
