# 真实代码迭代：人工审核记录 BDR v0.1

## Idea / real task

把已有挡护结构算量草稿接入一个真实的人工复核闭环：审核人能够逐项确认原图、设计依据、断面参数、单位/规则和工程部位，系统把复核动作、身份来源、备注、证据引用和时间写回同一份本地作业；AI 只读取状态和提醒缺口。

## Closest existing projects or capabilities

- 当前项目已有 `cad_qto.job`、MCP 工具、WebUI 和 `data/cad_jobs/*.json`；
- 当前项目已有钉钉身份与岗位审核能力，但尚未与 MCP 算量作业的复核记录统一；
- MCP/插件宿主只能负责调用工具，不能替代项目本地的状态和证据事实源；
- 开源 CAD 读写库只解决文件几何，不解决本项目的中文市政语义、挡护规则和审核追溯。

## Step 0 decision

`Integrate`：复用已有算量核心、作业文件、身份和 WebUI，只增加一个共用复核状态模块及两个入口（MCP、WebUI/API），不重写算量规则。

## Measurable improvement or differentiator

从“结果显示待审核”提升为“1 次明确复核提交写入 5 项检查、审核事件和状态回读”；复核作业可被 MCP、WebUI 和后续岗位系统读取，不再依靠聊天文本或手工另记。未经本地身份/授权条件满足，不能把 `Inference` 提升为 `Fact`。

## Success measure and required evidence

1. 复核 API 和 MCP 工具能拒绝不存在作业、非法检查项、缺少确认和项目越权；
2. `approve` 必须完成全部必核项，并写入 `review_history`、`review`、`review_status`；
3. 明确身份配置时可提升为 `Fact`，未配置时只能是 `REVIEWED_PENDING_AUTHORITY`；
4. 同一作业回读内容包含原图/标准化图哈希、规则版本、审核事件和最终状态；
5. 原有 DXF/挡护计算和插件 12 项基线不退化，并新增复核测试。

## Minimum Core

`cad_qto.review`：纯状态校验与复核事件生成；原子写入仍由入口层负责。允许的复核项、决定和状态转换集中在这里。

## Plugin boundaries

- MCP 增加 `municipal_qto_review_job`；
- WebUI/API 调用同一 `cad_qto.review`；
- 宿主身份通过本地环境变量或现有已认证成员传入；不在插件中自建账号、OAuth 或第二权限系统。

## Local-first boundary

复核只读写项目根目录内的 JSON 作业文件和本地审计事件；不调用模型、不上传图纸、不访问公共 URL。

## Data classification and local trust boundary

作业、审核人标识、备注、证据引用、图纸哈希属于 `PRIVATE_PROJECT_DATA`，只留在本地项目根目录；配置中的审核人标识不作为公共发布内容。

## GitHub/public release decision

`Blocked`：本次不发布、不推送、不生成包含真实项目资料的公共包。只交付源码和脱敏测试夹具；每个发布物仍需单独审查。

## External transfer plan

`N/A`。当前不需要外部传输；云端宿主仍只接入私有 MCP 网关，不把复核作业或图纸传到公共网络。

## State, change signals, and next-check rule

状态：`REVIEW_REQUIRED → REVIEWED_PENDING_AUTHORITY / FACT_CONFIRMED / RETURNED / REJECTED`。源图哈希、规则版本、输入断面、复核清单或审核人变化时重新读取；无变化不轮询。

## Observation / inference / hypothesis / fact boundary

- `Observation`：作业文件中已有的源图、实体、哈希、公式、输入和复核事件；
- `Hypothesis`：图层/文字识别候选；
- `Inference`：规则计算数量；
- `Fact`：只有全部必核项已确认且本地身份/授权条件通过，才允许标记。

## Evolution, validation, canary, version, and rollback plan

复核协议版本为 `cq-municipal-review-v0.1`；先用合成作业验证，再用脱敏真实项目双算和双审；错误时按作业文件备份回退，停用复核入口不删除原始图纸或历史作业。

## WebUI decision

`Required`：审核人员需要看到复核清单、结果状态和缺口。保持 `打开 → 输入 → 执行 → 结果`，复核字段只在算量结果后显示。

## Simplest reliable implementation

Python 标准库纯函数校验 + JSON 原子替换 + 现有 HTTP/MCP 入口；不增加数据库、消息队列、云 SDK 或模型依赖。

## Explicitly not building

不实现自动审核、不实现电子签名法律效力、不自建身份系统、不自动套重庆定额单价、不实现 DWG/PDF/OCR 转换，也不把复核结果自动写入结算或支付系统。
