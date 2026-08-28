# 本地转换与成果导出构建决策记录 v0.4

## 1. 真实任务

在 `sayelf-cq-municipal-cad-qto` 内，把 DXF 作为默认输入格式；允许单选或多选录入 PDF、DWG，并在本机将可转换文件转成 DXF 后进入现有道路、管网、挡护工程量计算链路；算量成果可独立下载为 Excel 或 PDF。真实图纸、原始文件、转换文件、作业和成果均属于本地项目数据，不进入 `sayelf-municipal-cost-loop`，不上传公共网络。

## 2. Step 0 调研与分类

当前工作区已有 ASCII DXF 解析、标准化、三专业确定性算量、证据与人工复核、WebUI 和 MCP 边界；缺口是本地输入转换与结果文件导出。

参考能力不是整套产品的重复建设：

- [ezdxf](https://github.com/mozman/ezdxf)：成熟的 DXF 读写与审计能力；本仓库继续使用现有轻量解析边界，不扩大为通用 CAD 平台。
- [PyMuPDF 矢量绘图提取](https://pymupdf.readthedocs.io/en/latest/recipes-drawing-and-graphics.html)：提供 PDF 路径/矩形等矢量图元读取；用于本地 PDF → DXF 适配器。
- [ODA File Converter](https://www.opendesign.com/GUESTFILES/ODA_FILE_CONVERTER)：可作为本机 DWG ↔ DXF 转换器；本仓库只调用已安装并显式配置的本地程序，不内置或上传 DWG。
- [LibreDWG](https://github.com/LibreDWG/libredwg)：开源 DWG/DXF 方向的可替换适配参考；不在本次把平台绑定到其构建、许可证或版本行为。

分类：**Improve**。复用现有 DXF 核心，增加可审查的本地输入适配和成果导出；不重建 CAD 识别器，不将文件转换结果冒充设计语义。

## 3. Build Decision Record

- **决定**：PDF 采用本地矢量图元提取后生成 ASCII DXF；DWG 采用本机 ODA/LibreDWG 等转换器适配器，未发现转换器时明确失败；DXF 不转换。原始文件与转换 DXF 同时留存并记录 SHA-256、方式、告警。
- **可测差异**：已有 DXF 算量链路不改规则；新增 `.pdf/.dwg` 可进入同一检查/算量入口；成果可分别下载 `.xlsx/.pdf`；转换失败不产生可计算假结果。
- **成功证据**：合成矢量 PDF 能生成可解析 DXF；无 DWG 转换器时返回可行动错误；上传接口支持单/多文件并保留双哈希；导出的 Excel/PDF 可被标准工具打开；原有回归测试保持通过。
- **最小 Core**：`conversion.py`、`export.py`、上传转换元数据、两个下载格式、现有作业证据扩展。保持道路/管网/挡护规则不变。
- **插件边界**：MCP 增加本地转换和本地成果导出工具；宿主只得到脱敏路径、哈希、状态和成果路径，不获得外部上传权限。
- **本地优先边界**：转换器、PDF 解析、输出生成全部在本机进程完成；不调用云端 OCR、在线 CAD 服务或远程文件接口。
- **数据分类**：原始图纸、转换 DXF、作业 JSON、导出文件为 `Sensitive/Restricted`；代码、合成样例、schema 和本记录为 `Public`。缺失分类不得推送 GitHub。
- **GitHub 决策**：只提交代码、脱敏文档和合成测试；不提交 `data/cad_inputs`、`data/cad_jobs`、真实图纸、导出成果、转换器安装包或日志。
- **状态/检查规则**：转换结果是 `Observation`，PDF 图元映射告警必须进入复核；专业候选是 `Hypothesis`，算量是 `Inference`，人工确认后才可成为 `Fact`。
- **演进/回滚**：转换适配器按格式隔离；移除本次新增模块和路由即可回退到 DXF-only，原有 DXF 规则与作业不改。
- **WebUI**：保留 `打开 → 输入 → 执行 → 结果`；文件入口默认突出 DXF，PDF/DWG 显示“本地转换为 DXF”；结果区提供独立 Excel/PDF 下载。
- **最简单实现**：标准库 multipart/HTTP、PyMuPDF（可选能力检测）、报告 PDF 生成、无数据库的本地文件；不引入任务队列、云服务或复杂前端框架。
- **明确不做**：不实现通用 DWG 解析器、不对扫描 PDF 做未经确认的 OCR/猜测、不自动套重庆定额/清单/综合单价、不自动入账、不打通岗位成果闭环项目。

## 4. 风险与待验证项

PDF 转 DXF 只对能提取到矢量线段/文字的 PDF 负责；扫描件或复杂嵌入 CAD 图元会带有告警或拒绝进入算量。DWG 的成功率取决于本机转换器版本、许可证和命令行行为，必须用脱敏样本在部署机验收。
