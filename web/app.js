const state = { bootstrap: null, data: null, role: "construction_survey", cadJobId: "", cadStatus: null };

const cadSample = [{
  section_id: "R-001", station_start: "K0+000", station_end: "K0+030", length_m: 30,
  wall_type: "重力式挡墙", wall_material: "片石混凝土", wall_height_m: 4,
  wall_base_width_m: 2.2, wall_top_width_m: 0.6, foundation_width_m: 2.4,
  foundation_thickness_m: 0.5, excavation_area_m2_per_m: 3, backfill_area_m2_per_m: 2,
  drainage_hole_spacing_m: 5, filter_area_m2_per_m: 0.8, anchor_spacing_m: 10,
  anchor_rows: 2, anchor_length_m: 8, pile_count: 4, pile_width_m: 0.8,
  pile_depth_m: 0.8, pile_length_m: 6, shotcrete_area_m2_per_m: 0.5,
  shotcrete_thickness_m: 0.1
}];

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));

async function getJSON(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "请求失败");
  return payload;
}

async function postJSON(url, body) {
  const response = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "提交失败");
  return payload;
}

function roleName(code) { return state.bootstrap.roles.find((role) => role.code === code)?.name || code; }
function roleLine(code) { return state.bootstrap.roles.find((role) => role.code === code)?.line || ""; }
function statusClass(status) {
  if (["验证合格", "已进入造价系统", "APPROVED", "FACT_CONFIRMED"].includes(status)) return "good";
  if (["证据不足", "数据冲突", "退回补证", "RETURNED", "REJECTED"].includes(status)) return "bad";
  if (["待造价验证", "待交叉验证", "待本线审核", "REVIEW_REQUIRED", "REVIEWED_PENDING_AUTHORITY"].includes(status)) return "warn";
  return "";
}

async function refresh() {
  state.data = await getJSON(`/api/state?role=${encodeURIComponent(state.role)}`);
  renderProjectIdentity(); renderDashboard(); renderTasks(); renderRecords(); renderCadSummary();
}

function renderProjectIdentity() {
  const project = state.data.project;
  $("#projectName").textContent = project.project_name;
  $("#projectCardName").textContent = project.project_name;
  $("#projectCardId").textContent = `${project.project_id} · ${project.status === "active" ? "进行中" : project.status}`;
  $("#projectIdentity").innerHTML = [
    ["项目编号", project.project_id], ["合同编号", project.contract_no],
    ["造价系统编号", project.cost_system_project_no], ["当前岗位", roleName(state.role)]
  ].map(([label, value]) => `<div class="identity-item"><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join("");
}

function renderDashboard() {
  const summary = state.data.summary;
  const metrics = [
    ["本期任务", summary.task_count, "当前岗位可见任务"],
    ["已提交成果", summary.record_count, "已形成项目记录"],
    ["待审核 / 互证", summary.pending_review, "需要生产或技术处理"],
    ["待造价验证", summary.cost_queue, "通过前置审核后进入"]
  ];
  $("#metrics").innerHTML = metrics.map(([label, value, hint]) => `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${esc(value)}</div><div class="metric-hint">${hint}</div></div>`).join("");
  const pending = summary.pending_review + summary.cost_queue;
  $("#nextTitle").textContent = pending ? "先处理待审核成果" : (summary.record_count ? "继续补齐项目证据" : "先提交第一项成果");
  $("#nextBadge").textContent = pending ? `${pending} 项待处理` : "工作面可开始";
  $("#statusNote").textContent = state.data.records.length ? `当前岗位可见 ${state.data.records.length} 条成果记录，其中 ${summary.verified} 条已完成造价验证。` : "当前还没有成果记录，建议先提交一条现场成果，观察完整审核链路。";
  $("#nextActions").innerHTML = pending ? `<button class="button button-outline" data-go="records">查看待审核 <span>→</span></button>` : `<button class="button button-outline" data-go="submit">提交岗位成果 <span>→</span></button><button class="button button-outline" data-go="cad">试算挡护结构 <span>↗</span></button>`;
  $("#nextActions").querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.go)));
}

function renderTasks() {
  const tasks = state.data.tasks.filter((task) => task.role_code === state.role);
  $("#myTasks").innerHTML = tasks.length ? tasks.slice(0, 5).map((task) => `<div class="task-row"><div class="task-main"><div class="task-title">${esc(task.title)}</div><div class="task-meta">${esc(task.requirement)} · ${esc(task.boq_code || "综合任务")}</div></div><span class="task-tag">${esc(task.period)}</span></div>`).join("") : `<div class="empty">当前岗位暂无任务</div>`;
  $("#taskSelect").innerHTML = tasks.map((task) => `<option value="${esc(task.task_id)}">${esc(task.title)}</option>`).join("") || `<option value="">暂无可提交任务</option>`;
  const categories = state.bootstrap.categories[state.role] || [roleName(state.role)];
  $("#categorySelect").innerHTML = categories.map((category) => `<option>${esc(category)}</option>`).join("");
}

function renderRecords() {
  const records = state.data.records;
  $("#recordsList").innerHTML = records.length ? records.slice().reverse().map((record) => {
    const canLineReview = ["production_manager", "technical_lead"].includes(state.role) && ["待本线审核", "待交叉验证"].includes(record.status);
    const canCost = state.role === "cost_manager" && record.status === "待造价验证";
    const actions = [
      canLineReview ? `<button data-review="${esc(record.record_id)}" data-line="${esc(roleLine(state.role))}">本线通过</button>` : "",
      canLineReview ? `<button data-return="${esc(record.record_id)}" data-line="${esc(roleLine(state.role))}">退回补证</button>` : "",
      canCost ? `<button data-cost="${esc(record.record_id)}">造价合格</button>` : "",
      canCost ? `<button data-cost-return="${esc(record.record_id)}">造价退回</button>` : ""
    ].join("");
    return `<div class="record-row"><div class="record-main"><div class="record-title">${esc(record.description)} <small>${esc(roleName(record.role_code))}</small></div><div class="record-meta">${esc(record.work_date)} · ${esc(record.location || "未填部位")} · ${esc(record.actual_quantity || "未填数量")} ${esc(record.unit || "")}<span class="evidence-count">证据 ${record.evidence.length} 份</span></div></div><div class="record-actions"><span class="status ${statusClass(record.status)}">${esc(record.status)}</span>${actions}</div></div>`;
  }).join("") : `<div class="empty">当前还没有成果记录</div>`;
}

function renderCadSummary() {
  const jobs = state.cadJobs || [];
  const latest = jobs[0];
  $("#cadSummary").innerHTML = [
    ["识别范围", state.cadStatus?.input_formats?.join("、") || "ASCII DXF", "项目内相对路径"],
    ["规则包", state.cadStatus?.retaining_rule_pack || "cq-municipal-retaining-v0.1", "确定性规则计算"],
    ["最近作业", latest?.job_id || "尚未执行", latest ? latest.review_status : "等待输入"],
    ["审核门", latest?.status || "REVIEW_REQUIRED", "人工复核后才可确认"]
  ].map(([title, value, hint]) => `<div class="summary-chip"><b>${esc(title)}：${esc(value)}</b><small>${esc(hint)}</small></div>`).join("");
}

function renderCadStatus() {
  const status = state.cadStatus;
  if (!status) return;
  $("#cadStatusLine").textContent = `${status.input_formats.join("、")} · ${status.retaining_rule_pack} · 必须人工复核`;
}

function renderCadJobs() {
  const jobs = state.cadJobs || [];
  $("#cadJobs").innerHTML = jobs.length ? jobs.slice(0, 8).map((job) => `<div class="job-row"><div><b>${esc(job.job_id)} · ${esc(job.source_file)}</b><small>${esc(job.created_at)} · ${esc(job.rule_pack_version)} · 告警 ${esc(job.warning_count)}</small></div><span class="status ${statusClass(job.status)}">${esc(job.review_status || job.status)}</span></div>`).join("") : `<div class="empty">本项目还没有 CAD 算量作业</div>`;
}

async function loadCad() {
  const [status, jobs] = await Promise.all([getJSON("/api/cad/status"), getJSON("/api/cad/jobs")]);
  state.cadStatus = status; state.cadJobs = jobs.jobs || [];
  renderCadStatus(); renderCadJobs(); renderCadSummary();
}

function setupNavigation() {
  document.querySelectorAll(".nav-btn").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.go)));
}

function showView(view) {
  document.querySelectorAll(".nav-btn").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  document.querySelectorAll(".view").forEach((section) => section.classList.toggle("active", section.id === `view-${view}`));
  window.scrollTo({top: 0, behavior: "smooth"});
}

async function fileToData(file) {
  return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve({name: file.name, type: file.type || "现场照片", data: reader.result}); reader.onerror = reject; reader.readAsDataURL(file); });
}

async function submitRecord(event) {
  event.preventDefault(); const form = event.target; const data = Object.fromEntries(new FormData(form).entries());
  data.role_code = state.role; data.evidence = await Promise.all([...$("#evidenceInput").files].slice(0, 5).map(fileToData));
  try { await postJSON("/api/records", data); $("#formMessage").textContent = "已提交，记录进入本线审核。"; form.reset(); $("[name=work_date]").value = new Date().toISOString().slice(0, 10); await refresh(); showView("records"); }
  catch (error) { $("#formMessage").textContent = error.message; }
}

async function handleRecordAction(event) {
  const button = event.target; const reviewId = button.dataset.review; const returnId = button.dataset.return; const costId = button.dataset.cost; const costReturnId = button.dataset.costReturn;
  try {
    if (reviewId) await postJSON("/api/reviews", {record_id: reviewId, review_line: button.dataset.line, result: "通过", reviewer_user_id: `demo-${button.dataset.line}`});
    if (returnId) await postJSON("/api/reviews", {record_id: returnId, review_line: button.dataset.line, result: "退回补证", reviewer_user_id: `demo-${button.dataset.line}`});
    if (costId) await postJSON("/api/cost-validation", {record_id: costId, result: "合格", reviewer_user_id: "demo-cost"});
    if (costReturnId) await postJSON("/api/cost-validation", {record_id: costReturnId, result: "退回补证", reviewer_user_id: "demo-cost"});
    await refresh();
  } catch (error) { window.alert(error.message); }
}

async function generateReport() { try { const payload = await getJSON(`/api/report?role=${encodeURIComponent(state.role)}`); $("#reportOutput").textContent = payload.report; } catch (error) { $("#reportOutput").textContent = error.message; } }

function renderCadResult(job) {
  state.cadJobId = job.job_id; const totals = job.calculation.totals || [];
  const candidateLayers = (job.recognition.candidates || []).map((candidate) => `${candidate.layer} → ${candidate.candidate_groups.join("、")}`).join("；") || "未匹配到专业图层";
  const warningLines = [...(job.source.warnings || []), ...(job.calculation.warnings || []).map((warning) => `${warning.section_id}: ${warning.message}`)];
  const lines = [`作业：${job.job_id}`, `状态：${job.status} / ${job.calculation.review_status}`, `源图：${job.source.source_file}`, `源图 SHA-256：${job.source.source_sha256}`, `标准化 DXF：${job.source.canonical_file}`, `标准化图 SHA-256：${job.source.canonical_sha256}`, `规则包：${job.calculation.rule_pack_version}`, `候选图层（Hypothesis）：${candidateLayers}`, `告警：${warningLines.length ? warningLines.join("；") : "无"}`, "", "工程量合计（Inference，待人工审核）：", ...totals.map((total) => `- ${total.item_code} | ${total.item} | ${total.quantity} ${total.unit}`), "", `审核状态：${job.review?.status || "REVIEW_REQUIRED"} / ${job.calculation.review_status}`, "审核要求：核对原图、设计说明、断面表、工程部位和规则输入；通过本地身份校验后才可成为 Fact。"];
  $("#cadOutput").textContent = lines.join("\n"); $("#cadReviewPanel").hidden = false; $("#cadReviewerId").value = state.bootstrap.current_member?.user_id || `demo-${state.role}`; $("#cadReviewerRole").value = ["production", "technical", "cost", "project_manager"].includes(roleLine(state.role)) ? roleLine(state.role) : "project_manager";
}

async function submitCad(event) {
  event.preventDefault(); const form = event.target; let sections;
  try { sections = JSON.parse($("#cadSections").value); if (!Array.isArray(sections)) throw new Error("断面参数必须是 JSON 数组"); }
  catch (error) { $("#cadMessage").textContent = `断面参数格式不正确：${error.message}`; return; }
  try { const payload = await postJSON("/api/cad/retaining", {source_file: form.elements.source_file.value, sections}); document.querySelectorAll("[data-review-check]").forEach((input) => { input.checked = false; }); $("#cadReviewNote").value = ""; $("#cadReviewMessage").textContent = ""; renderCadResult(payload.job); $("#cadMessage").textContent = `算量完成，生成 ${payload.summary.quantity_count} 条明细；当前仍需人工审核。`; await loadCad(); }
  catch (error) { $("#cadMessage").textContent = error.message; }
}

async function submitCadReview(decision) {
  if (!state.cadJobId) { $("#cadReviewMessage").textContent = "请先执行一次挡护结构算量。"; return; }
  if (!window.confirm(decision === "approve" ? "确认已完成全部复核项并提交通过吗？" : "确认退回该算量作业补充资料吗？")) return;
  const checkedItems = [...document.querySelectorAll("[data-review-check]:checked")].map((input) => input.value);
  try { const payload = await postJSON(`/api/cad/jobs/${encodeURIComponent(state.cadJobId)}/review`, {reviewer_id: $("#cadReviewerId").value.trim(), reviewer_role: $("#cadReviewerRole").value, decision, checked_items: checkedItems, note: $("#cadReviewNote").value.trim(), confirm: true}); renderCadResult(payload.job); $("#cadReviewMessage").textContent = `复核已落盘：${payload.job.status} / ${payload.job.calculation.review_status}`; await loadCad(); await refresh(); }
  catch (error) { $("#cadReviewMessage").textContent = error.message; }
}

async function init() {
  state.bootstrap = await getJSON("/api/bootstrap"); if (state.bootstrap.current_member) state.role = state.bootstrap.current_member.role_code;
  $("#roleSelect").innerHTML = state.bootstrap.roles.map((role) => `<option value="${esc(role.code)}">${esc(role.name)}</option>`).join(""); $("#roleSelect").value = state.role;
  if (state.bootstrap.mode !== "local_demo") { $("#roleSelect").disabled = true; $("#roleSelect").closest(".role-picker").style.display = "none"; }
  $("[name=work_date]").value = new Date().toISOString().slice(0, 10); $("#cadSections").value = JSON.stringify(cadSample, null, 2); setupNavigation();
  $("#roleSelect").addEventListener("change", async (event) => { state.role = event.target.value; await refresh(); }); $("#recordForm").addEventListener("submit", submitRecord); $("#recordsList").addEventListener("click", handleRecordAction); $("#refreshBtn").addEventListener("click", refresh); $("#reportBtn").addEventListener("click", generateReport); $("#cadForm").addEventListener("submit", submitCad); $("#cadApproveBtn").addEventListener("click", () => submitCadReview("approve")); $("#cadReturnBtn").addEventListener("click", () => submitCadReview("return")); $("#resetBtn").addEventListener("click", async () => { if (window.confirm("确定重置本地演示数据吗？")) { await postJSON("/api/reset-demo", {}); await refresh(); await loadCad(); } });
  await refresh(); await loadCad();
}

init().catch((error) => { const formal = /钉钉|认证|企业成员|实名/.test(error.message) || new URLSearchParams(window.location.search).get("mode") === "dingtalk"; const action = formal ? `<a class="button button-primary" href="/auth/dingtalk/start">使用钉钉企业账号登录</a>` : ""; document.body.innerHTML = `<main style="padding:40px;font-family:system-ui"><h2>${formal ? "请先完成钉钉登录" : "系统启动失败"}</h2><p>${esc(error.message)}</p>${action}<p>本地演示请确认已通过 server.py 启动服务。</p></main>`; });
