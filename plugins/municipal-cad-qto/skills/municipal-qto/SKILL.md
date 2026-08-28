---
name: municipal-qto
description: Use the local municipal CAD quantity-takeoff tools for Chongqing road, drainage, earthwork and retaining structures. Apply when the user asks to inspect DXF drawings, normalize CAD files, calculate retaining quantities, explain formulas, or prepare review evidence.
---

# 重庆市政 CAD 工程量辅助

使用本技能时遵循以下顺序：

1. 先调用 `municipal_qto_capabilities`，确认当前宿主、输入格式、规则版本和数据边界。
2. 对 DXF 先调用 `municipal_qto_inspect_dxf`，检查图层、实体、文字和未支持实体。
3. 只有在需要生成副本时调用 `municipal_qto_normalize_dxf`；不得覆盖原始图纸。
4. 只有取得人工确认的断面参数后，才调用 `municipal_qto_calculate_retaining`。
5. 计算后调用 `municipal_qto_get_job`，完整展示公式、输入、SHA-256、告警和审核状态。
6. 只有用户明确完成核对并确认后，才调用 `municipal_qto_review_job`；通过前必须勾选原图、设计依据、断面参数、单位/规则和工程部位五项。
7. 复核后再次调用 `municipal_qto_get_job`，报告 `REVIEWED_PENDING_AUTHORITY`、`FACT_CONFIRMED`、`RETURNED` 或 `REJECTED` 的实际状态。
8. 最终回答必须说明：识别结果是 `Hypothesis`、计算结果是 `Inference`；未通过本地身份核验的审核不得作为 `Fact`。

安全约束：

- 只使用项目私有根目录内的相对路径；路径越界、公开 URL、非 DXF 输入或缺少关键尺寸时停止并说明原因。
- 不猜测设计意图、地质参数、重庆定额子目、单价或结算口径。
- 不上传真实图纸、合同、照片、人员信息或造价文件到外部模型、公共网络或第三方 API。
- 发现未支持实体、单位异常、图层语义不唯一或规则版本变化时，把问题列为人工复核项。
