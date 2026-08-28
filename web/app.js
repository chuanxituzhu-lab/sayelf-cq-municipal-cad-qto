const state = { bootstrap: null, data: null, role: "construction_survey", cadJobId: "" };

const cadSample = [{
  section_id: "R-001",
  station_start: "K0+000",
  station_end: "K0+030",
  length_m: 30,
  wall_type: "重力式挡墙",
  wall_material: "片石混凝土",
  wall_height_m: 4,
  wall_base_width_m: 2.2,
  wall_top_width_m: 0.6,
  foundation_width_m: 2.4,
  foundation_thickness_m: 0.5,
  excavation_area_m2_per_m: 3,
  backfill_area_m2_per_m: 2,
  drainage_hole_spacing_m: 5,
  filter_area_m2_per_m: 0.8,
  anchor_spacing_m: 10,
  anchor_rows: 2,
  anchor_length_m: 8,
  pile_count: 4,
  pile_width_m: 0.8,
  pile_depth_m: 0.8,
  pile_length_m: 6,
  shotcrete_area_m2_per_m: 0.5,
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

function roleName(code) {
  return state.bootstrap.roles.find((role) => role.code === code)?.name || code;
}

function roleLine(code) {
  return state.bootstrap.roles.find((role) => role.code === code)?.line || "";
}

function statusClass(status) {
  if (["验证合格", "已进入造价系统"].includes(status)) return "good";
  if (["证据不足", "数据冲突", "退回补证"].includes(status)) return "bad";
  if (["待造价验证", "待交叉验证"].includes(status)) return "warn";
  return "";
}

async function refresh() {
  state.data = await getJSON(`/api/state?role=${encodeURIComponent(state.role)}`);
  renderDashboard();
  renderRecords();
  renderTasks();
}

function renderDashboard() {
  const summary = state.data.summary;
  $("#metrics").innerHTML = [
    ["本期任务", summary.task_count, "项目任务基线"],
    ["已提交成果", summary.record_count, "岗位已形成记录"],
    ["待审核/互证", summary.pending_review, "生产或技术线待处理"],
    ["待造价验证", summary.cost_queue, "三证互证后进入"],
  ].map(([label, value, hint]) => `<div class="metric"><div class="label">${label}</div><div class="value">${value}</div><div class="hint">${hint}</div></div>`).join("");
  const records = state.data.records;
  $("#statusNote").textContent = records.length ? `当前岗位可见 ${records.length} 条成果记录。造价合格记录：${summary.verified} 条。` : "还没有成果记录，先提交一条现场成果验证流程。";
}

function renderTasks() {
  const tasks = state.data.tasks.filter((task) => task.role_code === state.role);
  $("#myTasks").innerHTML = tasks.length ? tasks.map((task) => `<div class="task-row"><div><div class="task-title">${esc(task.title)}</div><div class="task-meta">${esc(task.requirement)} · ${esc(task.boq_code || "综合任务")}</div></div><span class="tag">${esc(task.period)}</span></div>`).join("") : `<div class="empty">当前岗位暂无任务</div>`;
  $("#taskSelect").innerHTML = tasks.map((task) => `<option value="${esc(task.task_id)}">${esc(task.title)}</option>`).join("") || `<option value="">暂无可提交任务</option>`;
  const categories = state.bootstrap.categories[state.role] || [roleName(state.role)];
  $("#categorySelect").innerHTML = categories.map((category) => `<option>${esc(category)}</option>`).join("");
}

function renderRecords() {
  const records = state.data.records;
  $("#recordsList").innerHTML = records.length ? records.slice().reverse().map((record) => {
    const canLineReview = ["production_manager", "technical_lead"].includes(state.role) && ["待本线审核", "待交叉验证"].includes(record.status);
    const canCost = state.role === "cost_manager" && record.status === "待造价验证";
    const action = [
      canLineReview ? `<button data-review="${esc(record.record_id)}" data-line="${esc(roleLine(state.role))}">本线通过</button>` : "",
      canLineReview ? `<button data-return="${esc(record.record_id)}" data-line="${esc(roleLine(state.role))}">退回补证</button>` : "",
      canCost ? `<button data-cost="${esc(record.record_id)}">造价合格</button>` : "",
      canCost ? `<button data-cost-return="${esc(record.record_id)}">造价退回</button>` : "",
    ].join("");
    return `<div class="record-row"><div class="record-main"><div class="record-title">${esc(record.description)} <small>${esc(roleName(record.role_code))}</small></div><div class="record-meta">${esc(record.work_date)} · ${esc(record.location || "未填部位")} · ${esc(record.actual_quantity || "未填数量")} ${esc(record.unit || "")} <span class="evidence-count">证据 ${record.evidence.length} 份</span></div></div><div class="record-actions"><span class="status ${statusClass(record.status)}">${esc(record.status)}</span>${action}</div></div>`;
  }).join("") : `<div class="empty">当前还没有成果记录</div>`;
}

function setupNavigation() {
  document.querySelectorAll(".nav-btn").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.go)));
}

function showView(view) {
  document.querySelectorAll(".nav-btn").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  document.querySelectorAll(".view").forEach((section) => section.classList.toggle("active", section.id === `view-${view}`));
}

async function fileToData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({name: file.name, type: file.type || "现场照片", data: reader.result});
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function submitRecord(event) {
  event.preventDefault();
  const form = event.target;
  const data = Object.fromEntries(new FormData(form).entries());
  data.role_code = state.role;
  data.evidence = await Promise.all([...$("#evidenceInput").files].slice(0, 5).map(fileToData));
  try {
    await postJSON("/api/records", data);
    $("#formMessage").textContent = "已提交，记录进入本线审核。";
    form.reset();
    $("[name=work_date]").value = new Date().toISOString().slice(0, 10);
    await refresh();
    showView("records");
  } catch (error) {
    $("#formMessage").textContent = error.message;
  }
}

async function handleRecordAction(event) {
  const reviewId = event.target.dataset.review;
  const returnId = event.target.dataset.return;
  const costId = event.target.dataset.cost;
  const costReturnId = event.target.dataset.costReturn;
  try {
    if (reviewId) await postJSON("/api/reviews", {record_id: reviewId, review_line: event.target.dataset.line, result: "通过", reviewer_user_id: `demo-${event.target.dataset.line}`});
    if (returnId) await postJSON("/api/reviews", {record_id: returnId, review_line: event.target.dataset.line, result: "退回补证", reviewer_user_id: `demo-${event.target.dataset.line}`});
    if (costId) await postJSON("/api/cost-validation", {record_id: costId, result: "合格", reviewer_user_id: "demo-cost"});
    if (costReturnId) await postJSON("/api/cost-validation", {record_id: costReturnId, result: "退回补证", reviewer_user_id: "demo-cost"});
    await refresh();
  } catch (error) {
    window.alert(error.message);
  }
}

async function generateReport() {
  const payload = await getJSON("/api/report");
  $("#reportOutput").textContent = payload.report;
}

function renderCadResult(job) {
  state.cadJobId = job.job_id;
  const totals = job.calculation.totals || [];
  const candidateLayers = (job.recognition.candidates || []).map((candidate) => `${candidate.layer} → ${candidate.candidate_groups.join("、")}`).join("；") || "未匹配到专业图层";
  const warningLines = [...(job.source.warnings || []), ...(job.calculation.warnings || []).map((warning) => `${warning.section_id}: ${warning.message}`)];
  const lines = [
    `作业：${job.job_id}`,
    `状态：${job.status} / ${job.calculation.review_status}`,
    `源图：${job.source.source_file}`,
    `源图 SHA-256：${job.source.source_sha256}`,
    `标准化 DXF：${job.source.canonical_file}`,
    `标准化图 SHA-256：${job.source.canonical_sha256}`,
    `候选图层：${candidateLayers}`,
    `告警：${warningLines.length ? warningLines.join("；") : "无"}`,
    "",
    "工程量合计（Inference，待人工审核）：",
    ...totals.map((total) => `- ${total.item_code} | ${total.item} | ${total.quantity} ${total.unit}`),
    "",
    `审核状态：${job.review?.status || "REVIEW_REQUIRED"} / ${job.calculation.review_status}`,
    "审核要求：核对原图、设计说明、断面表、工程部位和规则输入；通过本地身份校验后才可成为 Fact。"
  ];
  $("#cadOutput").textContent = lines.join("\n");
  $("#cadReviewPanel").hidden = false;
  $("#cadReviewerId").value = state.bootstrap.current_member?.user_id || `demo-${state.role}`;
  $("#cadReviewerRole").value = ["production", "technical", "cost", "project_manager"].includes(roleLine(state.role)) ? roleLine(state.role) : "project_manager";
}

async function submitCad(event) {
  event.preventDefault();
  const form = event.target;
  let sections;
  try {
    sections = JSON.parse($("#cadSections").value);
    if (!Array.isArray(sections)) throw new Error("断面参数必须是 JSON 数组");
  } catch (error) {
    $("#cadMessage").textContent = `断面参数格式不正确：${error.message}`;
    return;
  }
  try {
    const body = {source_file: form.elements.source_file.value, sections};
    const payload = await postJSON("/api/cad/retaining", body);
    document.querySelectorAll("[data-review-check]").forEach((input) => { input.checked = false; });
    $("#cadReviewNote").value = "";
    $("#cadReviewMessage").textContent = "";
    renderCadResult(payload.job);
    $("#cadMessage").textContent = `算量完成，生成 ${payload.summary.quantity_count} 条明细；当前仍需人工审核。`;
  } catch (error) {
    $("#cadMessage").textContent = error.message;
  }
}

async function submitCadReview(decision) {
  if (!state.cadJobId) {
    $("#cadReviewMessage").textContent = "请先执行一次挡护结构算量。";
    return;
  }
  if (!window.confirm(decision === "approve" ? "确认已完成全部复核项并提交通过吗？" : "确认退回该算量作业补充资料吗？")) return;
  const checkedItems = [...document.querySelectorAll("[data-review-check]:checked")].map((input) => input.value);
  try {
    const payload = await postJSON(`/api/cad/jobs/${encodeURIComponent(state.cadJobId)}/review`, {
      reviewer_id: $("#cadReviewerId").value.trim(),
      reviewer_role: $("#cadReviewerRole").value,
      decision,
      checked_items: checkedItems,
      note: $("#cadReviewNote").value.trim(),
      confirm: true
    });
    renderCadResult(payload.job);
    $("#cadReviewMessage").textContent = `复核已落盘：${payload.job.status} / ${payload.job.calculation.review_status}`;
  } catch (error) {
    $("#cadReviewMessage").textContent = error.message;
  }
}

async function init() {
  state.bootstrap = await getJSON("/api/bootstrap");
  if (state.bootstrap.current_member) state.role = state.bootstrap.current_member.role_code;
  $("#projectName").textContent = state.bootstrap.project.project_name;
  $("#roleSelect").innerHTML = state.bootstrap.roles.map((role) => `<option value="${esc(role.code)}">${esc(role.name)}</option>`).join("");
  $("#roleSelect").value = state.role;
  if (state.bootstrap.mode !== "local_demo") {
    $("#roleSelect").disabled = true;
    $("#roleSelect").closest(".role-picker").style.display = "none";
  }
  $("[name=work_date]").value = new Date().toISOString().slice(0, 10);
  $("#cadSections").value = JSON.stringify(cadSample, null, 2);
  setupNavigation();
  $("#roleSelect").addEventListener("change", async (event) => { state.role = event.target.value; await refresh(); });
  $("#recordForm").addEventListener("submit", submitRecord);
  $("#recordsList").addEventListener("click", handleRecordAction);
  $("#refreshBtn").addEventListener("click", refresh);
  $("#reportBtn").addEventListener("click", generateReport);
  $("#cadForm").addEventListener("submit", submitCad);
  $("#cadApproveBtn").addEventListener("click", () => submitCadReview("approve"));
  $("#cadReturnBtn").addEventListener("click", () => submitCadReview("return"));
  $("#resetBtn").addEventListener("click", async () => { if (window.confirm("确定重置本地演示数据吗？")) { await postJSON("/api/reset-demo", {}); await refresh(); } });
  await refresh();
}

init().catch((error) => {
  const formal = /钉钉|认证|企业成员|实名/.test(error.message) || new URLSearchParams(window.location.search).get("mode") === "dingtalk";
  const action = formal ? `<a class="primary" href="/auth/dingtalk/start">使用钉钉企业账号登录</a>` : "";
  document.body.innerHTML = `<main style="padding:40px;font-family:system-ui"><h2>${formal ? "请先完成钉钉登录" : "系统启动失败"}</h2><p>${esc(error.message)}</p>${action}<p>本地演示请确认已通过 server.py 启动服务。</p></main>`;
});
