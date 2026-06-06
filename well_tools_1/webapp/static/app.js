// Vanilla ES module frontend — no framework, no build step.
// Three views: mode select -> inputs -> workspace (form + preview).

const $ = (id) => document.getElementById(id);

const els = {
  // mode
  modeReport: $("modeReport"),
  modeInterval: $("modeInterval"),
  // interval generator
  pickXml: $("pickXml"),
  xmlPath: $("xmlPath"),
  pickTemplate: $("pickTemplate"),
  templatePath: $("templatePath"),
  intervalGenerate: $("intervalGenerate"),
  intervalStatus: $("intervalStatus"),
  intervalPreview: $("intervalPreview"),
  // inputs
  pickExcel: $("pickExcel"),
  excelPath: $("excelPath"),
  workingDirInput: $("workingDirInput"),
  browseFolder: $("browseFolder"),
  toWorkspace: $("toWorkspace"),
  inputsStatus: $("inputsStatus"),
  // workspace
  inputsSummary: $("inputsSummary"),
  wellName: $("wellName"),
  config: $("configSelect"),
  damageCount: $("damageCount"),
  templateHint: $("templateHint"),
  generate: $("generate"),
  status: $("status"),
  previewPanel: $("previewPanel"),
  previewMeta: $("previewMeta"),
  previewBody: $("previewBody"),
};

const state = {
  templates: [],
  templatesLoaded: false,
  excelPath: null,
};

const ivState = { xmlPath: null, templatePath: null };

// --- pywebview bridge -------------------------------------------------------
function pyapi() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

// --- View navigation --------------------------------------------------------
const VIEWS = ["mode", "interval", "inputs", "workspace"];
function showView(name) {
  for (const v of VIEWS) {
    const el = document.getElementById(`view-${v}`);
    if (el) el.hidden = v !== name;
  }
}

// --- Template registry ------------------------------------------------------
async function ensureTemplates() {
  if (state.templatesLoaded) return;
  const res = await fetch("/api/templates");
  if (!res.ok) throw new Error(`Failed to load templates (HTTP ${res.status})`);
  state.templates = await res.json();
  state.templatesLoaded = true;
  populateConfigOptions();
}

function populateConfigOptions() {
  const configs = [...new Set(state.templates.map((t) => t.config_key))].sort();
  els.config.innerHTML = "";
  for (const c of configs) {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    els.config.appendChild(opt);
  }
  refreshTemplateHint();
}

function resolveTemplate() {
  // Configuration alone selects the template; damages are independent (N).
  const configKey = els.config.value;
  return state.templates.find((t) => t.config_key === configKey) || null;
}

function refreshTemplateHint() {
  const t = resolveTemplate();
  if (t) {
    els.templateHint.textContent = `Template: ${t.name}`;
    els.templateHint.classList.remove("hint-warn");
    els.generate.disabled = false;
  } else {
    els.templateHint.textContent = "No template found for this configuration.";
    els.templateHint.classList.add("hint-warn");
    els.generate.disabled = true;
  }
}

function damageCountValue() {
  const n = parseInt(els.damageCount.value, 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

// --- Inputs view ------------------------------------------------------------
async function pickExcel() {
  const api = pyapi();
  if (!api) return inputsError("Native file dialogs are only available in the desktop app.");
  const path = await api.pick_file(["Excel files (*.xlsx;*.xlsm)", "All files (*.*)"]);
  if (path) {
    state.excelPath = path;
    els.excelPath.textContent = path;
    els.excelPath.classList.remove("muted");
  }
}

async function browseFolder() {
  const api = pyapi();
  if (!api) return inputsError("Native folder dialogs are only available in the desktop app.");
  const path = await api.pick_folder();
  if (path) els.workingDirInput.value = path;
}

async function toWorkspace() {
  const workingDir = els.workingDirInput.value.trim();
  if (!state.excelPath) return inputsError("Please choose an Excel data file.");
  if (!workingDir) return inputsError("Please provide a working directory.");

  hide(els.inputsStatus);
  try {
    await ensureTemplates();
  } catch (err) {
    return inputsError(err.message || String(err));
  }
  els.inputsSummary.textContent = `Excel: ${basename(state.excelPath)}  •  Folder: ${workingDir}`;
  showView("workspace");
}

function inputsError(msg) {
  els.inputsStatus.hidden = false;
  els.inputsStatus.className = "status error";
  els.inputsStatus.innerHTML = `<strong>Error:</strong> ${escapeHtml(msg)}`;
}

// --- Generate ---------------------------------------------------------------
async function generate() {
  const template = resolveTemplate();
  if (!template) return showError("No template found for this configuration.");
  const workingDir = els.workingDirInput.value.trim();
  if (!state.excelPath) return showError("Excel data file is missing — go back and choose one.");
  if (!workingDir) return showError("Working directory is missing — go back and set one.");

  setLoading(true);
  showInfo("Generating report…");

  try {
    const res = await fetch("/api/report/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template_id: template.id,
        excel_path: state.excelPath,
        working_dir: workingDir,
        well_name: els.wellName.value.trim() || null,
        damage_count: damageCountValue(),
      }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showError(data && data.detail ? data.detail : `HTTP ${res.status}`);
      return;
    }
    showSuccess(data);
  } catch (err) {
    showError(`Request failed: ${err.message || err}`);
  } finally {
    setLoading(false);
  }
}

async function reveal(path) {
  const api = pyapi();
  if (api) await api.reveal_file(path);
}

// --- Preview ----------------------------------------------------------------
async function requestPreview(runId) {
  els.previewPanel.hidden = false;
  els.previewMeta.textContent = "";
  els.previewBody.innerHTML =
    `<div class="preview-status"><span class="spinner"></span> Rendering preview…</div>`;

  try {
    const res = await fetch(`/api/preview/${runId}`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data && data.detail ? data.detail : `HTTP ${res.status}`;
      els.previewBody.innerHTML =
        `<div class="preview-status preview-error">Preview unavailable: ${escapeHtml(detail)}</div>`;
      return;
    }
    renderPreview(data);
  } catch (err) {
    els.previewBody.innerHTML =
      `<div class="preview-status preview-error">Preview request failed: ${escapeHtml(err.message || err)}</div>`;
  }
}

function renderPreview(data) {
  els.previewMeta.textContent = `${data.page_count} page${data.page_count === 1 ? "" : "s"}`;
  els.previewBody.innerHTML = "";
  data.pages.forEach((src, i) => {
    const img = document.createElement("img");
    img.className = "preview-page";
    img.src = src;
    img.alt = `Page ${i + 1}`;
    els.previewBody.appendChild(img);
  });
}

// --- Status rendering -------------------------------------------------------
function showStatus(kind, html) {
  els.status.hidden = false;
  els.status.className = `status ${kind}`;
  els.status.innerHTML = html;
}
function showInfo(msg) {
  showStatus("info", `<span class="spinner"></span> ${escapeHtml(msg)}`);
}
function showError(msg) {
  showStatus("error", `<strong>Error:</strong> ${escapeHtml(msg)}`);
}
function showSuccess(data) {
  showStatus(
    "success",
    `<strong>Report created</strong>
     <div class="result-path">${escapeHtml(data.output_path)}</div>
     <button id="revealBtn" type="button" class="secondary">Reveal in file manager</button>`
  );
  const btn = $("revealBtn");
  if (btn) btn.addEventListener("click", () => reveal(data.output_path));
  requestPreview(data.run_id);
}

function setLoading(loading) {
  els.generate.disabled = loading || !resolveTemplate();
  els.generate.textContent = loading ? "Working…" : "Generate Report";
}

// --- Interval Generator -----------------------------------------------------
async function pickXml() {
  const api = pyapi();
  if (!api) return intervalError("Native file dialogs are only available in the desktop app.");
  const p = await api.pick_file(["XML files (*.xml)", "All files (*.*)"]);
  if (p) {
    ivState.xmlPath = p;
    els.xmlPath.textContent = p;
    els.xmlPath.classList.remove("muted");
  }
}

async function pickTemplate() {
  const api = pyapi();
  if (!api) return intervalError("Native file dialogs are only available in the desktop app.");
  const p = await api.pick_file(["Excel files (*.xlsx;*.xlsm)", "All files (*.*)"]);
  if (p) {
    ivState.templatePath = p;
    els.templatePath.textContent = p;
    els.templatePath.classList.remove("muted");
  }
}

async function intervalGenerate() {
  if (!ivState.xmlPath) return intervalError("Please choose a WellSchematic XML file.");
  if (!ivState.templatePath) return intervalError("Please choose an Excel template.");

  setIntervalLoading(true);
  intervalStatus("info", `<span class="spinner"></span> Generating Raw Data…`);
  els.intervalPreview.hidden = true;

  try {
    const res = await fetch("/api/interval/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        xml_path: ivState.xmlPath,
        template_path: ivState.templatePath,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      intervalError(data && data.detail ? data.detail : `HTTP ${res.status}`);
      return;
    }
    intervalSuccess(data);
  } catch (err) {
    intervalError(`Request failed: ${err.message || err}`);
  } finally {
    setIntervalLoading(false);
  }
}

function intervalSuccess(data) {
  const types = Object.entries(data.pipe_types)
    .map(([k, v]) => `${v} ${k}`)
    .join(", ");
  intervalStatus(
    "success",
    `<strong>Raw Data updated in place</strong>
     <div class="result-path">${escapeHtml(data.template_path)}</div>
     <div class="iv-summary">${data.num_pipes} pipes (${escapeHtml(types)}) • ${data.num_intervals} intervals • ${data.depth_min.toFixed(0)}–${data.depth_max.toFixed(0)} ft<br>${escapeHtml(data.thickness_note)}</div>
     <button id="ivRevealBtn" type="button" class="secondary">Reveal in file manager</button>`
  );
  const btn = $("ivRevealBtn");
  if (btn) btn.addEventListener("click", () => reveal(data.template_path));
  els.intervalPreview.hidden = false;
  els.intervalPreview.textContent = data.preview;
}

function intervalStatus(kind, html) {
  els.intervalStatus.hidden = false;
  els.intervalStatus.className = `status ${kind}`;
  els.intervalStatus.innerHTML = html;
}
function intervalError(msg) {
  intervalStatus("error", `<strong>Error:</strong> ${escapeHtml(msg)}`);
}
function setIntervalLoading(loading) {
  els.intervalGenerate.disabled = loading;
  els.pickXml.disabled = loading;
  els.pickTemplate.disabled = loading;
  els.intervalGenerate.textContent = loading ? "Working…" : "Generate Raw Data";
}

// --- Helpers ----------------------------------------------------------------
function hide(el) { el.hidden = true; }
function basename(p) { return String(p).split(/[\\/]/).pop(); }
function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- Wire up ----------------------------------------------------------------
els.modeReport.addEventListener("click", () => showView("inputs"));
els.modeInterval.addEventListener("click", () => showView("interval"));
document.querySelectorAll("[data-nav]").forEach((b) =>
  b.addEventListener("click", () => showView(b.getAttribute("data-nav")))
);

els.pickXml.addEventListener("click", pickXml);
els.pickTemplate.addEventListener("click", pickTemplate);
els.intervalGenerate.addEventListener("click", intervalGenerate);

els.pickExcel.addEventListener("click", pickExcel);
els.browseFolder.addEventListener("click", browseFolder);
els.toWorkspace.addEventListener("click", toWorkspace);

els.config.addEventListener("change", refreshTemplateHint);
els.generate.addEventListener("click", generate);

showView("mode");
