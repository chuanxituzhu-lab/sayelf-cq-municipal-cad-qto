# 三专业 CAD 造量与仓库隔断构建决策记录

版本：v0.3
日期：2026-08-28
适用仓库：`sayelf-cq-municipal-cad-qto`

## 1. Idea / real task

本仓库只做 CAD 图纸工程量计算，服务造价人员核对：

```text
本地 DXF 文件录入（单选/多选）
  → 图纸检查与标准化
  → 道路 / 管网 / 挡护结构分类
  → 人工确认的断面或构件参数
  → 确定性几何算量
  → 工程量、公式、哈希、告警和审核状态
```

`sayelf-cq-municipal-cad-qto` 与 `sayelf-municipal-cost-loop` 必须是两个独立且隔断的仓库。本仓库不导入、不调用、不共享另一个仓库的代码、数据库、项目目录、身份体系、工作记录、报告或 API；本仓库的本地数据根目录固定为自身目录下的 `data/`。

## 2. Step 0：现有能力与缺口

已检查当前工作区、GitHub 和开源生态。可复用的方向包括：

- 道路走廊、纵横断面和排水设计工具：可参考 [CorridorRoad](https://github.com/ganadara135/CorridorRoad) 的专业边界；
- 工程图纸量取与来源证据：可参考 [OpenConstructionERP quantity takeoff](https://github.com/datadrivenconstruction/OpenConstructionERP/blob/main/docs/user-guide/quantity-takeoff.md)；
- 工程图纸识别和数量证据：可参考 [Takeoff-Lens-Plugin](https://github.com/anekhirun/Takeoff-Lens-Plugin) 的来源关联思路；
- 管网拓扑清理：可参考 [network-topology-qgis](https://github.com/Oksion/network-topology-qgis) 的节点和线网质量提醒。

这些项目没有直接提供“本地中文市政 DXF + 重庆规则 + 道路/管网/挡护统一算量 + 人工证据门 + AI 插件”的可直接复用成品。

本次分类：**Improve**。

## 3. 可量化改进与成功证据

1. 一个本地入口可以录入 1 个或多个 DXF 文件，并返回每个文件的私有路径标签、源图 SHA-256 和图纸检查结果。
2. 同一份 `cad_qto` 核心新增道路、管网、挡护三类确定性几何规则；同一输入可重复得到同一结果。
3. 每条工程量保留专业类型、分项编码、公式、单位、输入快照、源图哈希、规则包版本和审核状态。
4. 缺少关键尺寸、未支持实体、图层语义不唯一或单位异常时停在 `Hypothesis/Inference/REVIEW_REQUIRED`，不补猜。
5. WebUI 能完成 `打开 → 录入文件 → 检查 → 选择专业 → 输入参数 → 计算 → 结果`；MCP 与 HTTP API 调用同一核心。

## 4. Minimum Core

```text
cad_qto.dxf / canonical / recognition
  → cad_qto.road
  → cad_qto.network
  → cad_qto.retaining
  → cad_qto.job
  → cad_qto.review
```

首版规则边界：

- 道路：路面面积/体积、基层、底基层、路基挖方、路基填方、明确输入的路缘石；
- 管网：管道长度、沟槽开挖、垫层、管道占用体积、沟槽回填、检查井/雨水口明确数量；
- 挡护：墙身、基础、开挖、回填、泄水孔、反滤层、锚杆/锚索、抗滑桩、喷射混凝土、钢筋网；
- 文件：当前只接受本地 ASCII DXF；DWG/PDF/IFC/LandXML 保持为未来独立适配器，不在本次伪装支持。

## 5. Plugin boundaries and repository isolation

- `cad_qto/`：唯一的专业无关确定性核心；
- `server.py`、`web/`：本仓库本地 WebUI 和 API；
- `plugins/municipal-cad-qto/`：本仓库的 MCP/宿主适配器；
- `data/`：本仓库的私有输入、标准化图、作业和审核结果；
- `sayelf-municipal-cost-loop`：不作为依赖、上游、下游或共享数据库；若未来需要交付，只能由人工审核后导出公开定义的结果文件，且必须另行授权和审查。

## 6. Local-first and data boundary

本地文件上传只写入当前仓库的 `data/cad_inputs/`，检查和计算在本地完成。真实图纸、计价文件、合同、项目数据和审核信息属于 `Sensitive/Restricted`，不进入 GitHub、不传给外部模型、不复制到 cost-loop 仓库。只发布代码、合成 DXF、脱敏文档和公开规则说明。

## 7. State and evidence

文件状态：`LOCAL_SELECTED → STORED_PRIVATE → PARSED → NORMALIZED`。

算量状态：`DRAFT → CALCULATED → REVIEW_REQUIRED → FACT_CONFIRMED/RETURNED/REJECTED`。

`Observation` 是文件、实体、图层、文字和人工输入；`Hypothesis` 是专业候选；`Inference` 是公式数量；`Fact` 只能来自完成复核且通过可信身份核验的结果。

## 8. WebUI decision

WebUI 必须保留，因为文件录入、批量检查、专业选择、参数确认、证据查看和人工复核需要可视化控制。普通路径为：

```text
打开 → 录入文件（单选/多选） → 检查 → 选择专业 → 执行 → 结果 → 复核
```

## 9. Simplest reliable implementation

Python 标准库 + 现有 ASCII DXF 解析器 + 三个轻量规则模块 + 本地 multipart 文件入口 + 原生 HTML/CSS/JavaScript。暂不引入视觉模型、云端 OCR、复杂 CAD SDK、定额数据库或第二套项目系统。

## 10. Explicitly not building

- 不把 `sayelf-municipal-cost-loop` 合并进本仓库；
- 不建设岗位成果、项目管理、周报/月报、即时通讯、身份平台；
- 不根据图层名称直接认定专业和工程量；
- 不自动套重庆定额、综合单价、结算口径或自动入账；
- 不宣称当前版本支持 DWG/PDF/BIM 全自动识别。
