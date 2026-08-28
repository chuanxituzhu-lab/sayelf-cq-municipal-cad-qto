# sayelf-cq-municipal-cad-qto

重庆市政 CAD 工程量计算工具（造价算量）。本仓库把项目内 DXF 图纸（默认）以及本地转换后的 PDF/DWG 和人工确认的专业参数转换为可追溯的工程量计算草稿，服务造价人员复核；不承担岗位成果管理、项目管理或自动结算。

## 与 `sayelf-municipal-cost-loop` 的边界

两个仓库必须独立且隔断。本仓库不导入、不调用、不共享 `sayelf-municipal-cost-loop` 的代码、数据库、项目目录、身份体系、工作记录、报告或 API。图纸、算量作业和审核记录只写入本仓库自己的 `data/` 私有目录；公开仓库只包含代码、合成样例、插件契约和脱敏文档。

## 核心工作流

```text
打开
  → 单选 / 多选 DXF 文件录入（PDF / DWG 本地转 DXF）
  → 逐张检查、识别候选、保留源图哈希
  → 可选生成标准化 DXF 副本
  → 人工确认道路 / 管网 / 挡护参数
  → 确定性计算工程量
  → 查看公式、输入、哈希、告警和作业
  → 人工复核
  → 独立下载 Excel / PDF 成果
```

默认输入为项目内 ASCII DXF，支持 `LINE`、`LWPOLYLINE`、`TEXT`、`MTEXT`。文件入口支持单选或多选；PDF 使用本地 PyMuPDF 提取矢量图元生成 DXF，DWG 使用本机 ODA File Converter / ezdxf odafc（未安装则明确失败）。原始文件与转换 DXF 均保留，并记录双 SHA-256。单个文件逐一形成独立作业；批量检查不会把不同文件混成一个算量结果。

## 当前算量范围

### 道路工程

规则包：`cq-municipal-road-v0.1`。

- 路面面层、基层、底基层；
- 路基挖方、填方；
- 路缘石、侧平石/人行道；
- 输入长度、车行道宽度、厚度等人工确认参数后，按断面和长度计算。

### 管网工程

规则包：`cq-municipal-network-v0.1`。

- 管道长度与管道体积；
- 沟槽开挖、砂石垫层、回填；
- 检查井、雨水口；
- 道路恢复面积；
- 输入管径、沟槽宽深、构筑物数量等人工确认参数后计算。

### 挡护工程

规则包：`cq-municipal-retaining-v0.1`。

- 挡墙墙身、基础、基坑开挖、墙背回填；
- 泄水孔、反滤层；
- 锚杆/锚索、抗滑桩；
- 喷射混凝土、钢筋网/挂网。

三类结果都带有分项编码、单位、数量、公式、输入快照、规则包版本、源图哈希、告警和审核状态。

## 本地 WebUI

```text
python server.py
```

打开 <http://127.0.0.1:8765/>，按“文件录入 → 图纸检查 → 专业算量 → 结果复核”的工作面操作。

WebUI 的上传文件与转换副本只保存到当前仓库的 `data/cad_inputs/`，算量作业保存到 `data/cad_jobs/`，独立成果保存到 `data/cad_exports/`；服务不会读取或上传另一个 cost-loop 仓库的数据。建议先使用合成样例：

```text
图纸：fixtures/cq_retaining_demo.dxf
挡护参数：fixtures/cq_retaining_demo.json 中的 sections
道路/管网参数：见 WebUI 自动填入的示例，可替换为人工确认值
```

## 本地 CLI

兼容旧版挡护样例的 CLI：

```text
python -m cad_qto --input fixtures/cq_retaining_demo.json --output result.json
```

道路、管网、挡护综合算量优先通过 WebUI、HTTP API 或 MCP 工具提交数组参数。

## MCP / AI 宿主插件

插件目录为 [`plugins/municipal-cad-qto`](plugins/municipal-cad-qto)，只调用同一份 `cad_qto` 核心，不复制业务逻辑。当前统一工具包括：

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

Codex、Claude Code、WorkBuddy、千问/百炼、豆包/扣子等宿主只应接入本地 STDIO 或经过授权的私有 MCP。真实图纸、合同、计价文件和作业数据不得上传到公共网络或外部模型。

## 本地服务 API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/bootstrap` | 项目身份与能力清单 |
| GET | `/api/cad/status` | 输入、专业、规则包和审核门 |
| GET | `/api/cad/files` | 查看本地已录入文件 |
| POST | `/api/cad/files` | 单选/多选上传 DXF/PDF/DWG；非 DXF 在本地转为 DXF |
| POST | `/api/cad/convert` | 对项目内 PDF/DWG 执行本地转 DXF |
| POST | `/api/cad/inspect` | 检查单张 DXF |
| POST | `/api/cad/inspect-batch` | 批量检查多张 DXF |
| POST | `/api/cad/normalize` | 生成标准化 DXF 副本 |
| POST | `/api/cad/calculate` | 道路、管网、挡护综合算量 |
| POST | `/api/cad/retaining` | 旧版挡护算量兼容入口 |
| GET | `/api/cad/jobs` | 查看本地作业摘要 |
| GET | `/api/cad/jobs/{job_id}` | 查看完整结果 |
| POST | `/api/cad/jobs/{job_id}/review` | 记录人工复核 |
| GET | `/api/cad/jobs/{job_id}/export?format=xlsx` | 独立下载 Excel 成果 |
| GET | `/api/cad/jobs/{job_id}/export?format=pdf` | 独立下载 PDF 成果 |

## 可信和数据边界

- DXF 实体、图层、文字、哈希是 `Observation`；图层/文字专业候选是 `Hypothesis`；
- 依据人工确认参数和版本化公式计算的是 `Inference`；
- 通过原图、设计依据、专业参数、单位/规则、工程部位五项检查并完成本地身份核验后，才允许成为 `Fact`；
- 缺少关键尺寸、单位异常、未支持实体或数量告警时，不补猜，保留人工复核项；
- 真实文件属于 `Sensitive/Restricted`，只留在本地 `data/cad_inputs/`、`data/cad_jobs/`、`data/cad_exports/`，不进入 GitHub；
- 服务默认只监听 `127.0.0.1`，路径限制在项目根目录内。

本工具当前只做几何工程量，不自动套用重庆定额、清单、综合单价或结算口径；不对扫描 PDF 自动 OCR，不做设计意图推断、审批或入账。DWG 依赖本机转换器，不保证任何 DWG 无条件可转。

## 测试

```text
python -m unittest discover -s tests -v
python -m compileall -q server.py cad_qto plugins/municipal-cad-qto
node --check web/app.js
```

在合成样例、真实脱敏双算和人工验收完成前，不宣称生产级全自动算量。

## 文档

- [项目核心内容梳理](docs/项目核心内容梳理-v0.1.md)
- [三专业算量与仓库隔断 BDR](docs/三专业算量与仓库隔断-BDR-v0.3.md)
- [CAD 算量范围收敛 BDR](docs/CAD算量范围收敛-BDR-v0.2.md)
- [重庆市政图纸算量 BDR](docs/重庆市政图纸算量-BDR-v0.1.md)
- [字段与测试基线](docs/重庆市政图纸算量-字段与测试基线-v0.1.md)
- [跨平台插件 BDR](docs/跨平台AI插件-BDR-v0.1.md)
- [跨平台插件接入与验收](docs/跨平台AI插件-接入与验收-v0.1.md)
- [本地转换与成果导出 BDR](docs/本地转换与成果导出-BDR-v0.4.md)
