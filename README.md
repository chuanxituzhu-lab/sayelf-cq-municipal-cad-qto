# sayelf-cq-municipal-cad-qto

重庆市政 CAD 工程量计算工具（造价算量）。本仓库把项目内 DXF 图纸转换为可追溯的工程量计算草稿，重点服务造价人员的快速复核，不是项目管理、岗位成果或周报系统。

## 核心能力

```text
项目内 ASCII DXF
  → 检查图层、实体、文字和未支持实体
  → 生成标准化 DXF 副本
  → 图层语义候选（Hypothesis）
  → 人工确认挡护结构断面
  → 确定性工程量计算（Inference）
  → 公式、输入、哈希、告警和作业留痕
  → 人工复核后才可能成为 Fact
```

当前输入为 ASCII DXF，支持 `LINE`、`LWPOLYLINE`、`TEXT`、`MTEXT`。挡护结构规则包为 `cq-municipal-retaining-v0.1`，覆盖：

- 挡墙墙身、基础、基坑开挖、墙背回填；
- 泄水孔、反滤层；
- 锚杆/锚索、抗滑桩；
- 喷射混凝土、钢筋网/挂网。

当前只做几何工程量，不自动套用重庆定额、清单、综合单价或结算口径；不猜测设计意图、地质参数或缺失尺寸。

## 本地 WebUI

```text
python server.py
```

打开 <http://127.0.0.1:8765/>。

WebUI 的工作路径是：

```text
打开 → 输入 DXF → 检查/标准化 → 输入人工确认断面 → 执行 → 查看结果与证据 → 复核
```

可直接使用合成样例：

```text
图纸路径：fixtures/cq_retaining_demo.dxf
断面参数：fixtures/cq_retaining_demo.json 中的 sections
```

## 本地 CLI

```text
python -m cad_qto --input fixtures/cq_retaining_demo.json --output result.json
```

## MCP / AI 宿主插件

插件目录为 [`plugins/municipal-cad-qto`](plugins/municipal-cad-qto)，调用同一份 `cad_qto`，不复制业务逻辑。

工具包括：

```text
municipal_qto_capabilities
municipal_qto_inspect_dxf
municipal_qto_normalize_dxf
municipal_qto_calculate_retaining
municipal_qto_list_jobs
municipal_qto_get_job
municipal_qto_review_job
```

Codex、Claude Code、WorkBuddy 优先使用本地 STDIO MCP；千问、豆包等远程形态只能部署在经过授权的私有网络中。真实图纸、合同、计价文件和作业数据不得上传到公共网络。

## 本地服务 API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/bootstrap` | 项目身份与能力清单 |
| GET | `/api/cad/status` | 输入、规则包和审核门 |
| POST | `/api/cad/inspect` | 检查 DXF |
| POST | `/api/cad/normalize` | 生成标准化 DXF 副本 |
| POST | `/api/cad/retaining` | 计算挡护结构工程量草稿 |
| GET | `/api/cad/jobs` | 查看本地作业摘要 |
| GET | `/api/cad/jobs/{job_id}` | 查看完整结果 |
| POST | `/api/cad/jobs/{job_id}/review` | 记录人工复核 |

## 可信和数据边界

- 图层/文字识别是 `Hypothesis`；
- 依据人工确认断面和版本化公式计算的是 `Inference`；
- 通过五项人工检查且有本地已认证身份，才允许提升为 `Fact`；
- 原图、标准化图和作业 JSON 留在 `data/cad_jobs/`，该目录已被 Git 忽略；
- 路径必须是项目根目录内相对路径，不接受公开 URL 或目录外文件；
- 默认只监听 `127.0.0.1`。

## 测试

```text
python -m unittest discover -s tests -v
node --check web/app.js
node --check web/admin.js
```

在本地测试、真实脱敏双算和人工验收完成前，不宣称生产级全自动算量。

## 文档

- [项目核心内容梳理](docs/项目核心内容梳理-v0.1.md)
- [CAD 算量范围收敛 BDR](docs/CAD算量范围收敛-BDR-v0.2.md)
- [重庆市政图纸算量 BDR](docs/重庆市政图纸算量-BDR-v0.1.md)
- [字段与测试基线](docs/重庆市政图纸算量-字段与测试基线-v0.1.md)
- [跨平台插件 BDR](docs/跨平台AI插件-BDR-v0.1.md)
- [跨平台插件接入与验收](docs/跨平台AI插件-接入与验收-v0.1.md)
