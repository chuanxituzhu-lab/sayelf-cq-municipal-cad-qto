const state = { capabilities: null, jobs: [], selectedJobId: "", latestJob: null, files: [], selectedFiles: [] };

const sampleRoad = [{
  section_id: "RD-001", station_start: "K0+000", station_end: "K0+030", length_m: 30,
  road_type: "城市支路", carriageway_width_m: 7, surface_thickness_m: 0.18,
  base_thickness_m: 0.20, subbase_thickness_m: 0.20, roadbed_width_m: 9,
  cut_depth_m: 0.30, fill_depth_m: 0, curb_length_m: 60, sidewalk_area_m2: 90
}];

const sampleNetwork = [{
  segment_id: "PS-001", station_start: "K0+000", station_end: "K0+030", length_m: 30,
  network_type: "雨水管", pipe_outer_diameter_mm: 600, trench_width_m: 1.2,
  trench_depth_m: 1.8, bedding_thickness_m: 0.15, manhole_count: 2,
  inlet_count: 3, road_restoration_area_m2: 36
}];

const sampleRetaining = [{
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

async function request(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "请求失败");
  return payload;
}

function statusClass(value) {
  if (["FACT_CONFIRMED", "已人工审核"].includes(value)) return "good";
  if (["RETURNED", "REJECTED", "退回补充", "审核不通过"].includes(value)) return "bad";
  return "warn";
}

function showView(view) {
  document.querySelectorAll(".nav-button").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  document.querySelectorAll(".view").forEach((section) => section.classList.toggle("active", section.id === `view-${view}`));
  window.scrollTo({top: 0, behavior: "smooth"});
}

function message(selector, text, error = false) {
  const target = $(selector);
  if (!target) return;
  target.textContent = text;
  target.classList.toggle("error", error);
}

function renderCapabilities() {
  const c = state.capabilities;
  const dwgConverter = c.dwg_converter || {available: false, message: "DWG 转换器状态未知"};
  $("#ruleVersion").textContent = c.rule_pack_versions.join(" · ");
  $("#metrics").innerHTML = [
    ["输入格式", c.input_formats.join("、"), "默认 DXF；PDF / DWG 本地转 DXF"],
    ["文件入口", "单选 / 多选", "一次最多录入 50 个"],
    ["专业范围", c.disciplines.map((item) => ({road: "道路", network: "管网", retaining: "挡护"}[item] || item)).join(" · "), "统一算量核心"],
    ["审核门", "必须人工复核", "Inference 不自动入账"],
    ["DWG 转换", dwgConverter.available ? "本机可用" : "待安装", dwgConverter.message]
  ].map(([label, value, hint]) => `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(hint)}</small></div>`).join("");
  const groups = [
    ["道路工程", "road", c.road_scope],
    ["管网工程", "network", c.network_scope],
    ["挡护工程", "retaining", c.retaining_scope]
  ];
  $("#disciplineScope").innerHTML = groups.map(([title, key, items]) => `<div class="scope-card-wide"><strong>${esc(title)}</strong><small>${esc(items.join(" · "))}</small><span class="scope-code">${esc(key)}</span></div>`).join("");
}

function renderLatest() {
  const job = state.latestJob;
  $("#latestJob").innerHTML = job ? `<div class="latest-job"><b>${esc(job.job_id)} · ${esc(job.source_file)}</b><small>${esc(job.created_at)} · ${esc(job.rule_pack_version)} · ${esc(job.quantity_count)} 条明细 · 告警 ${esc(job.warning_count)}</small><span class="status ${statusClass(job.status)}">${esc(job.review_status || job.status)}</span></div>` : `<div class="latest-empty">还没有算量作业，先录入或检查一张 DXF。</div>`;
}

function renderJobs() {
  $("#jobsList").innerHTML = state.jobs.length ? state.jobs.map((job) => `<div class="job-row"><div><b>${esc(job.job_id)}</b><small>${esc(job.source_file)} · ${esc(job.rule_pack_version)} · ${esc(job.quantity_count)} 条明细 · 告警 ${esc(job.warning_count)}</small></div><div class="job-actions"><span class="status ${statusClass(job.status)}">${esc(job.review_status || job.status)}</span><button data-job="${esc(job.job_id)}" type="button">读取详情</button></div></div>`).join("") : `<div class="result-empty">本项目还没有算量作业。</div>`;
}

function renderReviewSelect() {
  $("#reviewJobSelect").innerHTML = `<option value="">请选择作业</option>${state.jobs.map((job) => `<option value="${esc(job.job_id)}">${esc(job.job_id)} · ${esc(job.source_file)}</option>`).join("")}`;
  if (state.selectedJobId) $("#reviewJobSelect").value = state.selectedJobId;
}

function renderSourceOptions() {
  const select = $("#calculateSourceSelect");
  const current = select.value;
  const usableFiles = state.files.filter((file) => file.input_format === "dxf" || file.conversion_status === "CONVERTED");
  const options = [{source_file: "fixtures/cq_retaining_demo.dxf", original_name: "合成样例"}].concat(usableFiles);
  const seen = new Set();
  select.innerHTML = options.filter((file) => !seen.has(file.source_file) && seen.add(file.source_file)).map((file) => `<option value="${esc(file.source_file)}">${esc(file.original_name || file.source_file)}${file.input_format && file.input_format !== "dxf" ? ` · ${esc(file.input_format.toUpperCase())}→DXF` : ""} · ${esc(file.source_file)}</option>`).join("");
  if ([...select.options].some((option) => option.value === current)) select.value = current;
}

function renderSelectedFiles() {
  const files = state.selectedFiles;
  $("#selectedFiles").innerHTML = files.length ? files.map((file) => `<span class="file-pill">${esc(file.name)} <small>${esc((file.name.split(".").pop() || "").toUpperCase())} · ${esc((file.size / 1024).toFixed(1))} KB</small></span>`).join("") : `<span class="muted">尚未选择文件。</span>`;
}

function renderBatchInspections(inspections, selector) {
  const target = $(selector);
  if (!target) return;
  if (!inspections.length) {
    target.innerHTML = `<div class="result-empty">尚未录入文件。</div>`;
    return;
  }
  target.className = "batch-result";
  target.innerHTML = inspections.map((item) => {
    if (item.status === "ERROR") return `<div class="batch-row error-row"><b>${esc(item.source_file)}</b><span>${esc(item.error)}</span></div>`;
    const inventory = item.geometry_inventory || {};
    const file = state.files.find((candidate) => candidate.source_file === item.source_file);
    const sourceLabel = file && file.original_file !== file.source_file ? `${file.original_name} · 本地转换 DXF ${file.source_file}` : item.source_file;
    return `<div class="batch-row"><b>${esc(sourceLabel)}</b><span>${esc(inventory.entity_count || 0)} 个支持实体 · ${esc(inventory.unsupported_entity_count || 0)} 个未支持实体 · ${item.review_required ? "需人工复核" : "已解析"}</span></div>`;
  }).join("");
}

async function refreshFiles() {
  const payload = await request("/api/cad/files");
  state.files = payload.files || [];
  renderSourceOptions();
}

async function uploadSelectedFiles() {
  if (!state.selectedFiles.length) {
    message("#fileMessage", "请先选择一个或多个 DXF、PDF 或 DWG 文件。", true);
    return;
  }
  const formData = new FormData();
  state.selectedFiles.forEach((file) => formData.append("files", file, file.name));
  const payload = await request("/api/cad/files", {method: "POST", body: formData});
  state.files = [...(payload.files || []), ...state.files];
  renderSourceOptions();
  message("#fileMessage", `已录入 ${payload.files.length} 个文件，文件仍在本项目私有目录。`);
  await inspectUploadedFiles("#batchInspectionResult");
  await inspectUploadedFiles("#batchInspectionResult2");
}

async function inspectUploadedFiles(selector = "#batchInspectionResult") {
  if (!state.files.length) {
    renderBatchInspections([], selector);
    message("#fileMessage", "暂无已录入文件，请先选择并录入 DXF、PDF 或 DWG。", true);
    return;
  }
  const messageSelector = selector === "#batchInspectionResult2" ? "#inspectMessage" : "#fileMessage";
  const inspectableFiles = state.files.filter((file) => file.input_format === "dxf" || file.conversion_status === "CONVERTED");
  const pendingFiles = state.files.filter((file) => !inspectableFiles.includes(file));
  const pendingInspections = pendingFiles.map((file) => ({
    status: "ERROR",
    source_file: file.original_file || file.source_file,
    error: file.conversion_status === "FAILED" ? "原始文件已保留；请安装本机 ODA File Converter 后重试 DWG→DXF。" : "文件必须先转换为 DXF 才能检查。"
  }));
  if (!inspectableFiles.length) {
    renderBatchInspections(pendingInspections, selector);
    message(messageSelector, "暂无可检查的 DXF；待转换文件已保留在本项目私有目录。", true);
    return;
  }
  const payload = await request("/api/cad/inspect-batch", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({source_files: inspectableFiles.map((file) => file.source_file)})});
  renderBatchInspections([...pendingInspections, ...(payload.inspections || [])], selector);
  message(messageSelector, `批量检查完成：${(payload.inspections || []).length} 个 DXF，待转换 ${pendingFiles.length} 个。`);
}

async function refreshJobs() {
  const payload = await request("/api/cad/jobs");
  state.jobs = payload.jobs || [];
  state.latestJob = state.jobs[0] || null;
  renderLatest();
  renderJobs();
  renderReviewSelect();
}

function renderInspection(result) {
  const inventory = result.geometry_inventory || {};
  const layers = inventory.layers || [];
  const unsupported = inventory.unsupported_entities || [];
  $("#inspectState").textContent = result.review_required ? "需人工复核" : "已解析";
  $("#inspectState").className = `state-chip ${result.review_required ? "warning" : ""}`;
  $("#inspectionResult").innerHTML = `<div class="inspection-grid"><div class="data-box"><span>源图</span><b>${esc(result.source_file)}</b></div><div class="data-box"><span>源图 SHA-256</span><b>${esc(result.source_sha256)}</b></div><div class="data-box"><span>单位代码</span><b>${esc(inventory.units_code || "未声明")}</b></div><div class="data-box"><span>支持实体</span><b>${esc(inventory.entity_count ?? 0)}</b></div><div class="data-box"><span>未支持实体</span><b>${esc(inventory.unsupported_entity_count ?? 0)}</b></div><div class="data-box"><span>图层数</span><b>${esc(layers.length)}</b></div></div><div class="candidate-list">${layers.map((layer) => `<div class="candidate-row"><b>${esc(layer.layer)}</b><span>${esc(Object.entries(layer.entity_types || {}).map(([key, value]) => `${key} × ${value}`).join("、"))} · 线长 ${esc(layer.linear_length)} · 文字 ${esc((layer.texts || []).join("；") || "无")}</span></div>`).join("") || `<div class="candidate-row"><span>未读取到图层</span></div>`}</div>${unsupported.length ? `<div class="warning-box">未支持实体：${unsupported.map((item) => `${esc(item.entity_type)} / ${esc(item.layer)}：${esc(item.reason)}`).join("；")}</div>` : `<div class="success-box">未发现未支持实体，可继续人工确认专业参数。</div>`}`;
}

function renderJob(job, target = "#calculationResult") {
  state.selectedJobId = job.job_id;
  const calculation = job.calculation || {};
  const source = job.source || {};
  const totals = calculation.totals || [];
  const quantities = calculation.quantities || [];
  const warnings = [...(source.warnings || []), ...(source.conversion_warnings || []), ...(calculation.warnings || []).map((item) => item.message || item)];
  const candidates = (job.recognition?.candidates || []).map((item) => `${item.layer} → ${(item.candidate_groups || []).join("、")}`).join("；") || "未匹配到专业图层";
  const disciplines = (calculation.disciplines || []).map((item) => ({road: "道路", network: "管网", retaining: "挡护"}[item] || item)).join(" · ");
  const conversion = source.conversion_status && source.conversion_status !== "NOT_NEEDED" ? `<div class="data-box"><span>输入转换</span><b>${esc(source.conversion_status)} · ${esc(source.conversion_method || "local")}</b><small>${esc(source.original_file || "")} · 原图 SHA ${esc(source.original_sha256 || "")}</small></div>` : "";
  const downloads = `<div class="download-actions"><span>独立成果下载</span><a class="outline" href="/api/cad/jobs/${encodeURIComponent(job.job_id)}/export?format=xlsx" download>下载 Excel</a><a class="outline" href="/api/cad/jobs/${encodeURIComponent(job.job_id)}/export?format=pdf" download>下载 PDF</a></div>`;
  $(target).innerHTML = `${downloads}<div class="evidence-grid"><div class="data-box"><span>作业状态</span><b class="status ${statusClass(job.status)}">${esc(job.status)}</b></div><div class="data-box"><span>计算专业</span><b>${esc(disciplines || "未指定")}</b></div><div class="data-box"><span>计算状态</span><b>${esc(calculation.review_status || "待人工审核")}</b></div><div class="data-box"><span>规则包</span><b>${esc(calculation.rule_pack_version)}</b></div><div class="data-box"><span>源图 SHA-256</span><b>${esc(source.source_sha256)}</b></div><div class="data-box"><span>标准化 DXF SHA-256</span><b>${esc(source.canonical_sha256)}</b></div><div class="data-box"><span>识别候选（Hypothesis）</span><b>${esc(candidates)}</b></div>${conversion}</div>${warnings.length ? `<div class="warning-box">告警：${warnings.map((item) => esc(item)).join("；")}</div>` : ""}<div class="quantity-table"><div class="quantity-row quantity-head"><span>编码</span><span>分项</span><span>单位</span><span>数量</span></div>${totals.map((item) => `<div class="quantity-row"><span>${esc(item.item_code)}</span><span>${esc(item.item)}</span><span>${esc(item.unit)}</span><span>${esc(item.quantity)}</span></div>`).join("")}</div><div class="formula-list">${quantities.slice(0, 50).map((item) => `<div class="formula-item">${esc(item.discipline)} / ${esc(item.item_code)}：${esc(item.formula)} = ${esc(item.quantity)} ${esc(item.unit)} · ${esc(item.status)}</div>`).join("")}</div>`;
  if (target === "#calculationResult") { $("#calculationState").textContent = calculation.review_status || job.status; $("#calculationState").className = `state-chip ${statusClass(job.status)}`; }
  if (target === "#reviewDetail") { $("#reviewState").textContent = job.status; $("#reviewState").className = `state-chip ${statusClass(job.status)}`; $("#reviewFormPanel").hidden = ["FACT_CONFIRMED", "REJECTED"].includes(job.status); $("#reviewerId").value = ""; }
}

async function inspect(sourceFile, messageSelector, render = true) {
  const payload = await request("/api/cad/inspect", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({source_file: sourceFile})});
  if (render) renderInspection(payload.inspection);
  message(messageSelector, `图纸检查完成：${payload.inspection.geometry_inventory.entity_count} 个支持实体，${payload.inspection.geometry_inventory.unsupported_entity_count} 个未支持实体。`);
  return payload.inspection;
}

async function normalize(sourceFile, messageSelector) {
  const outputFile = `data/cad_jobs/${sourceFile.split(/[\\/]/).pop().replace(/\.dxf$/i, ".canonical.dxf")}`;
  const payload = await request("/api/cad/normalize", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({source_file: sourceFile, output_file: outputFile})});
  message(messageSelector, `标准化副本已生成：${payload.manifest.canonical_file}；未覆盖原图。`);
}

function parseArray(selector, label) {
  const raw = $(selector).value.trim();
  if (!raw) return [];
  let value;
  try { value = JSON.parse(raw); } catch (error) { throw new Error(`${label} 参数格式不正确：${error.message}`); }
  if (!Array.isArray(value)) throw new Error(`${label} 参数必须是数组`);
  return value;
}

async function loadJob(jobId, target = "#reviewDetail") {
  const payload = await request(`/api/cad/jobs/${encodeURIComponent(jobId)}`);
  state.selectedJobId = jobId;
  renderJob(payload, target);
  return payload;
}

async function submitCalculation(event) {
  event.preventDefault();
  const form = event.target;
  try {
    const body = {
      source_file: form.elements.source_file.value,
      road_sections: parseArray("#roadSectionsInput", "道路"),
      network_sections: parseArray("#networkSectionsInput", "管网"),
      retaining_sections: parseArray("#retainingSectionsInput", "挡护")
    };
    if (!body.road_sections.length && !body.network_sections.length && !body.retaining_sections.length) throw new Error("至少填写一种专业参数数组");
    const payload = await request("/api/cad/calculate", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    renderJob(payload.job);
    message("#calculateMessage", `综合算量完成：${payload.summary.quantity_count} 条明细，当前为待人工审核。`);
    await refreshJobs();
  } catch (error) {
    message("#calculateMessage", error.message, true);
  }
}

async function submitReview(decision) {
  if (!state.selectedJobId) { message("#reviewMessage", "请先选择一个算量作业。", true); return; }
  if (decision === "approve" && !window.confirm("确认已完成全部五项复核并提交通过吗？")) return;
  const checkedItems = [...document.querySelectorAll("[data-check]:checked")].map((input) => input.value);
  try {
    const payload = await request(`/api/cad/jobs/${encodeURIComponent(state.selectedJobId)}/review`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({reviewer_id: $("#reviewerId").value.trim(), reviewer_role: $("#reviewerRole").value, decision, checked_items: checkedItems, note: $("#reviewNote").value.trim(), confirm: true})});
    renderJob(payload.job, "#reviewDetail");
    message("#reviewMessage", `复核已落盘：${payload.job.status} / ${payload.job.calculation.review_status}`);
    await refreshJobs();
  } catch (error) { message("#reviewMessage", error.message, true); }
}

function bind() {
  document.querySelectorAll(".nav-button").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.go)));
  $("#fileInput").addEventListener("change", (event) => { state.selectedFiles = [...event.target.files]; renderSelectedFiles(); });
  $("#fileDropzone").addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); $("#fileInput").click(); } });
  $("#fileEntryForm").addEventListener("submit", async (event) => { event.preventDefault(); try { await uploadSelectedFiles(); } catch (error) { message("#fileMessage", error.message, true); try { await refreshFiles(); } catch (_) { /* keep the original upload error visible */ } } });
  $("#inspectUploadedBtn").addEventListener("click", async () => { try { await inspectUploadedFiles("#batchInspectionResult"); } catch (error) { message("#fileMessage", error.message, true); } });
  $("#inspectUploadedBtn2").addEventListener("click", async () => { try { await inspectUploadedFiles("#batchInspectionResult2"); } catch (error) { message("#inspectMessage", error.message, true); } });
  $("#quickInspectForm").addEventListener("submit", async (event) => { event.preventDefault(); try { await inspect(event.target.elements.source_file.value, "#quickMessage", false); showView("inspect"); $("#inspectForm").elements.source_file.value = event.target.elements.source_file.value; await inspect(event.target.elements.source_file.value, "#inspectMessage"); } catch (error) { message("#quickMessage", error.message, true); } });
  $("#quickNormalizeBtn").addEventListener("click", async () => { try { await normalize($("#quickInspectForm").elements.source_file.value, "#quickMessage"); } catch (error) { message("#quickMessage", error.message, true); } });
  $("#inspectForm").addEventListener("submit", async (event) => { event.preventDefault(); try { await inspect(event.target.elements.source_file.value, "#inspectMessage"); } catch (error) { message("#inspectMessage", error.message, true); } });
  $("#normalizeBtn").addEventListener("click", async () => { try { await normalize($("#inspectForm").elements.source_file.value, "#inspectMessage"); } catch (error) { message("#inspectMessage", error.message, true); } });
  $("#calculateForm").addEventListener("submit", submitCalculation);
  $("#calculateInspectBtn").addEventListener("click", () => { $("#inspectForm").elements.source_file.value = $("#calculateSourceSelect").value; showView("inspect"); });
  $("#reviewJobSelect").addEventListener("change", (event) => { state.selectedJobId = event.target.value; });
  $("#loadReviewBtn").addEventListener("click", async () => { if (!state.selectedJobId) { message("#reviewLoadMessage", "请先选择作业。", true); return; } try { await loadJob(state.selectedJobId); message("#reviewLoadMessage", "作业详情已读取。"); } catch (error) { message("#reviewLoadMessage", error.message, true); } });
  $("#jobsList").addEventListener("click", async (event) => { const button = event.target.closest("[data-job]"); if (!button) return; state.selectedJobId = button.dataset.job; $("#reviewJobSelect").value = state.selectedJobId; showView("review"); try { await loadJob(state.selectedJobId); } catch (error) { message("#reviewLoadMessage", error.message, true); } });
  $("#refreshJobsBtn").addEventListener("click", refreshJobs);
  $("#approveBtn").addEventListener("click", () => submitReview("approve"));
  $("#returnBtn").addEventListener("click", () => submitReview("return"));
  $("#rejectBtn").addEventListener("click", () => submitReview("reject"));
}

async function init() {
  const bootstrap = await request("/api/bootstrap");
  state.capabilities = bootstrap;
  renderCapabilities();
  $("#roadSectionsInput").value = JSON.stringify(sampleRoad, null, 2);
  $("#networkSectionsInput").value = JSON.stringify(sampleNetwork, null, 2);
  $("#retainingSectionsInput").value = JSON.stringify(sampleRetaining, null, 2);
  bind();
  await refreshFiles();
  await refreshJobs();
}

init().catch((error) => { document.body.innerHTML = `<main style="padding:40px;font-family:system-ui"><h2>CAD 算量工作台启动失败</h2><p>${esc(error.message)}</p><p>请确认本地服务已通过 <code>python server.py</code> 启动。</p></main>`; });
