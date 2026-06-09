// Vanilla ES module frontend — no framework, no build step.
// Three views: mode select -> inputs -> workspace (form + preview).

const $ = (id) => document.getElementById(id);

const els = {
  // mode
  modeReport: $("modeReport"),
  modeInterval: $("modeInterval"),
  modeGhost: $("modeGhost"),
  // ghost merger
  ghostLength: $("ghostLength"),
  pickGhostCsv: $("pickGhostCsv"),
  ghostCsvPath: $("ghostCsvPath"),
  ghostMerge: $("ghostMerge"),
  ghostStatus: $("ghostStatus"),
  ghostPreview: $("ghostPreview"),
  // report-automation sub-feature entry points (on the inputs view)
  openTemplates: $("openTemplates"),
  openCompanies: $("openCompanies"),
  // template manager
  tmPickFile: $("tmPickFile"),
  tmFilePath: $("tmFilePath"),
  tmName: $("tmName"),
  tmConfigKey: $("tmConfigKey"),
  tmRegister: $("tmRegister"),
  tmStatus: $("tmStatus"),
  tmList: $("tmList"),
  // company manager
  cmPickFile: $("cmPickFile"),
  cmFilePath: $("cmFilePath"),
  cmName: $("cmName"),
  cmRegister: $("cmRegister"),
  cmStatus: $("cmStatus"),
  cmList: $("cmList"),
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
  logDate: $("logDate"),
  origComp: $("origComp"),
  lastWko: $("lastWko"),
  config: $("configSelect"),
  company: $("companySelect"),
  damageCount: $("damageCount"),
  includeDisclaimer: $("includeDisclaimer"),
  templateHint: $("templateHint"),
  companyHint: $("companyHint"),
  generate: $("generate"),
  status: $("status"),
  previewPanel: $("previewPanel"),
  previewMeta: $("previewMeta"),
  previewBody: $("previewBody"),
};

const state = {
  templates: [],
  templatesLoaded: false,
  companies: [],
  companiesLoaded: false,
  excelPath: null,
};

const ivState = { xmlPath: null, templatePath: null };
const ghostState = { csvPath: null };
const tmState = { filePath: null };
const cmState = { filePath: null };

// --- pywebview bridge -------------------------------------------------------
function pyapi() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

// --- View navigation --------------------------------------------------------
const VIEWS = ["mode", "interval", "ghost", "inputs", "workspace", "templates", "companies"];
function showView(name) {
  for (const v of VIEWS) {
    const el = document.getElementById(`view-${v}`);
    if (el) el.hidden = v !== name;
  }
  if (name === "templates") tmLoadList();
  if (name === "companies") cmLoadList();
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

async function ensureCompanies() {
  if (state.companiesLoaded) return;
  const res = await fetch("/api/companies");
  if (!res.ok) throw new Error(`Failed to load companies (HTTP ${res.status})`);
  state.companies = await res.json();
  state.companiesLoaded = true;
  populateCompanyOptions();
}

function populateCompanyOptions() {
  els.company.innerHTML = "";
  for (const c of state.companies) {
    const opt = document.createElement("option");
    opt.value = String(c.id);
    opt.textContent = c.name;
    els.company.appendChild(opt);
  }
  refreshCompanyHint();
}

function resolveCompany() {
  const id = parseInt(els.company.value, 10);
  return state.companies.find((c) => c.id === id) || null;
}

function refreshCompanyHint() {
  if (!state.companies.length) {
    els.companyHint.textContent =
      "No companies registered — add one in the Company Manager before generating.";
    els.companyHint.classList.add("hint-warn");
  } else {
    els.companyHint.textContent = "";
    els.companyHint.classList.remove("hint-warn");
  }
  updateGenerateEnabled();
}

function updateGenerateEnabled() {
  els.generate.disabled = !(resolveTemplate() && resolveCompany());
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
  } else {
    els.templateHint.textContent = "No template found for this configuration.";
    els.templateHint.classList.add("hint-warn");
  }
  updateGenerateEnabled();
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
    await ensureCompanies();
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
  const company = resolveCompany();
  if (!company) return showError("Please choose a company (or add one in the Company Manager).");
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
        company_id: company.id,
        include_disclaimer: els.includeDisclaimer.checked,
        log_date: els.logDate.value.trim() || null,
        orig_comp: els.origComp.value.trim() || null,
        last_wko: els.lastWko.value.trim() || null,
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
function noteClass(text) {
  const t = String(text).trim();
  if (t.startsWith("❌")) return "note-error";
  if (t.startsWith("⚠")) return "note-warn";
  if (t.startsWith("✎")) return "note-fix";
  return "note-info";
}

function renderNotes(notes) {
  if (!Array.isArray(notes) || notes.length === 0) return "";
  const issues = notes.filter((n) => noteClass(n) !== "note-info").length;
  const items = notes
    .map((n) => `<li class="${noteClass(n)}">${escapeHtml(String(n).trim())}</li>`)
    .join("");
  const label = issues
    ? `Report notes — ${issues} warning${issues === 1 ? "" : "s"}`
    : `Report notes (${notes.length})`;
  return `<details class="notes-panel"${issues ? " open" : ""}>
    <summary>${label}</summary>
    <ul class="notes-list">${items}</ul>
  </details>`;
}

function showSuccess(data) {
  const issues = (data.notes || []).filter((n) => noteClass(n) !== "note-info").length;
  const heading = issues
    ? `Report created · ${issues} warning${issues === 1 ? "" : "s"}`
    : "Report created";
  showStatus(
    "success",
    `<strong>${heading}</strong>
     <div class="result-path">${escapeHtml(data.output_path)}</div>
     <button id="revealBtn" type="button" class="secondary">Reveal in file manager</button>
     ${renderNotes(data.notes)}`
  );
  const btn = $("revealBtn");
  if (btn) btn.addEventListener("click", () => reveal(data.output_path));
  requestPreview(data.run_id);
}

function setLoading(loading) {
  els.generate.disabled = loading || !resolveTemplate() || !resolveCompany();
  els.generate.textContent = loading ? "Working…" : "Generate Report";
}

// --- Template Manager -------------------------------------------------------
async function tmPickFile() {
  const api = pyapi();
  if (!api) return tmShowStatus("error", "Native file dialogs are only available in the desktop app.");
  const p = await api.pick_file(["Word templates (*.docx)", "All files (*.*)"]);
  if (p) {
    tmState.filePath = p;
    els.tmFilePath.textContent = p;
    els.tmFilePath.classList.remove("muted");
    // Auto-fill config key from filename if the field is empty.
    if (!els.tmConfigKey.value.trim()) {
      const stem = p.split(/[\\/]/).pop().replace(/\.docx$/i, "");
      // strip leading "sample_N_" prefix if present, convert p→. and X→×
      const cleaned = stem
        .replace(/^sample_\d+_/i, "")
        .replace(/p/g, ".")
        .replace(/X/g, "×");
      els.tmConfigKey.value = cleaned;
    }
  }
}

async function tmRegister() {
  const name = els.tmName.value.trim();
  const configKey = els.tmConfigKey.value.trim();
  if (!tmState.filePath) return tmShowStatus("error", "Please choose a .docx file.");
  if (!name) return tmShowStatus("error", "Please enter a display name.");
  if (!configKey) return tmShowStatus("error", "Please enter a configuration key.");

  els.tmRegister.disabled = true;
  els.tmRegister.textContent = "Registering…";
  hide(els.tmStatus);

  try {
    const res = await fetch("/api/templates/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_path: tmState.filePath, name, config_key: configKey }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      tmShowStatus("error", data.detail || `HTTP ${res.status}`);
      return;
    }
    const verb = data.created ? "registered" : "updated";
    tmShowStatus("success", `✓ Template "${escapeHtml(data.name)}" ${verb} (${escapeHtml(data.config_key)})`);
    // Reset form.
    els.tmName.value = "";
    els.tmConfigKey.value = "";
    els.tmFilePath.textContent = "No file selected";
    els.tmFilePath.classList.add("muted");
    tmState.filePath = null;
    // Refresh list + invalidate report dropdown cache.
    state.templatesLoaded = false;
    await tmLoadList();
  } catch (err) {
    tmShowStatus("error", `Request failed: ${err.message || err}`);
  } finally {
    els.tmRegister.disabled = false;
    els.tmRegister.textContent = "Register Template";
  }
}

async function tmDelete(id, name) {
  if (!confirm(`Remove "${name}" from the registry?\n\nThe .docx file is kept on disk.`)) return;
  try {
    const res = await fetch(`/api/templates/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      tmShowStatus("error", data.detail || `HTTP ${res.status}`);
      return;
    }
    state.templatesLoaded = false;
    await tmLoadList();
  } catch (err) {
    tmShowStatus("error", `Delete failed: ${err.message || err}`);
  }
}

async function tmLoadList() {
  els.tmList.innerHTML = `<p class="tm-empty">Loading…</p>`;
  try {
    const res = await fetch("/api/templates");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rows = await res.json();
    if (!rows.length) {
      els.tmList.innerHTML = `<p class="tm-empty">No templates registered yet.</p>`;
      return;
    }
    els.tmList.innerHTML = "";
    rows.forEach((t) => {
      const row = document.createElement("div");
      row.className = "tm-row-item";
      row.innerHTML = `
        <div class="tm-info">
          <span class="tm-name">${escapeHtml(t.name)}</span>
          <span class="tm-key">${escapeHtml(t.config_key)}</span>
        </div>
        <button class="secondary tm-del-btn" data-id="${t.id}" data-name="${escapeHtml(t.name)}">Remove</button>`;
      row.querySelector(".tm-del-btn").addEventListener("click", (e) => {
        const btn = e.currentTarget;
        tmDelete(Number(btn.dataset.id), btn.dataset.name);
      });
      els.tmList.appendChild(row);
    });
  } catch (err) {
    els.tmList.innerHTML = `<p class="tm-empty" style="color:var(--error-fg)">Failed to load: ${escapeHtml(err.message)}</p>`;
  }
}

function tmShowStatus(kind, msg) {
  els.tmStatus.hidden = false;
  els.tmStatus.className = `status ${kind}`;
  els.tmStatus.innerHTML = escapeHtml(msg);
}

// --- Company Manager --------------------------------------------------------
async function cmPickFile() {
  const api = pyapi();
  if (!api) return cmShowStatus("error", "Native file dialogs are only available in the desktop app.");
  const p = await api.pick_file([
    "Image files (*.png;*.jpg;*.jpeg;*.tiff;*.tif;*.bmp;*.gif)",
    "All files (*.*)",
  ]);
  if (p) {
    cmState.filePath = p;
    els.cmFilePath.textContent = p;
    els.cmFilePath.classList.remove("muted");
    // Auto-fill the name from the filename if empty.
    if (!els.cmName.value.trim()) {
      els.cmName.value = p.split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
    }
  }
}

async function cmRegister() {
  const name = els.cmName.value.trim();
  if (!cmState.filePath) return cmShowStatus("error", "Please choose a logo image.");
  if (!name) return cmShowStatus("error", "Please enter a company name.");

  els.cmRegister.disabled = true;
  els.cmRegister.textContent = "Registering…";
  hide(els.cmStatus);

  try {
    const res = await fetch("/api/companies/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_path: cmState.filePath, name }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      cmShowStatus("error", data.detail || `HTTP ${res.status}`);
      return;
    }
    const verb = data.created ? "registered" : "updated";
    cmShowStatus("success", `✓ Company "${escapeHtml(data.name)}" ${verb}`);
    els.cmName.value = "";
    els.cmFilePath.textContent = "No file selected";
    els.cmFilePath.classList.add("muted");
    cmState.filePath = null;
    // Refresh list + invalidate report dropdown cache.
    state.companiesLoaded = false;
    await cmLoadList();
  } catch (err) {
    cmShowStatus("error", `Request failed: ${err.message || err}`);
  } finally {
    els.cmRegister.disabled = false;
    els.cmRegister.textContent = "Register Company";
  }
}

async function cmDelete(id, name) {
  if (!confirm(`Remove "${name}"?\n\nThe logo file is deleted from disk.`)) return;
  try {
    const res = await fetch(`/api/companies/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      cmShowStatus("error", data.detail || `HTTP ${res.status}`);
      return;
    }
    state.companiesLoaded = false;
    await cmLoadList();
  } catch (err) {
    cmShowStatus("error", `Delete failed: ${err.message || err}`);
  }
}

async function cmLoadList() {
  els.cmList.innerHTML = `<p class="tm-empty">Loading…</p>`;
  try {
    const res = await fetch("/api/companies");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rows = await res.json();
    if (!rows.length) {
      els.cmList.innerHTML = `<p class="tm-empty">No companies registered yet.</p>`;
      return;
    }
    els.cmList.innerHTML = "";
    rows.forEach((c) => {
      const row = document.createElement("div");
      row.className = "tm-row-item";
      row.innerHTML = `
        <div class="tm-info">
          <span class="tm-name">${escapeHtml(c.name)}</span>
          <span class="tm-key">${escapeHtml(basename(c.logo_path))}</span>
        </div>
        <button class="secondary tm-del-btn" data-id="${c.id}" data-name="${escapeHtml(c.name)}">Remove</button>`;
      row.querySelector(".tm-del-btn").addEventListener("click", (e) => {
        const btn = e.currentTarget;
        cmDelete(Number(btn.dataset.id), btn.dataset.name);
      });
      els.cmList.appendChild(row);
    });
  } catch (err) {
    els.cmList.innerHTML = `<p class="tm-empty" style="color:var(--error-fg)">Failed to load: ${escapeHtml(err.message)}</p>`;
  }
}

function cmShowStatus(kind, msg) {
  els.cmStatus.hidden = false;
  els.cmStatus.className = `status ${kind}`;
  els.cmStatus.innerHTML = escapeHtml(msg);
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

// --- Ghost Merger -----------------------------------------------------------
async function pickGhostCsv() {
  const api = pyapi();
  if (!api) return ghostError("Native file dialogs are only available in the desktop app.");
  const p = await api.pick_file(["CSV files (*.csv)", "All files (*.*)"]);
  if (p) {
    ghostState.csvPath = p;
    els.ghostCsvPath.textContent = p;
    els.ghostCsvPath.classList.remove("muted");
  }
}

async function ghostMerge() {
  if (!ghostState.csvPath) return ghostError("Please choose a Joint-Analysis CSV file.");
  const length = parseFloat(els.ghostLength.value);
  if (!Number.isFinite(length) || length <= 0) {
    return ghostError("Enter a valid ghost collar length greater than 0.");
  }

  setGhostLoading(true);
  ghostStatus("info", `<span class="spinner"></span> Merging ghost collars…`);
  els.ghostPreview.hidden = true;

  try {
    const res = await fetch("/api/ghost/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csv_path: ghostState.csvPath, ghost_collar_length: length }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      ghostError(data && data.detail ? data.detail : `HTTP ${res.status}`);
      return;
    }
    ghostSuccess(data);
  } catch (err) {
    ghostError(`Request failed: ${err.message || err}`);
  } finally {
    setGhostLoading(false);
  }
}

function ghostSuccess(data) {
  ghostStatus(
    "success",
    `<strong>Merged file saved</strong>
     <div class="result-path">${escapeHtml(data.output_path)}</div>
     <div class="iv-summary">${data.input_rows} joints → ${data.output_rows} rows • ${data.merged_chains} merged chain(s) • collars ≥ ${data.threshold} ft</div>
     <button id="ghostRevealBtn" type="button" class="secondary">Reveal in file manager</button>`
  );
  const btn = $("ghostRevealBtn");
  if (btn) btn.addEventListener("click", () => reveal(data.output_path));
  els.ghostPreview.hidden = false;
  els.ghostPreview.textContent = data.preview;
}

function ghostStatus(kind, html) {
  els.ghostStatus.hidden = false;
  els.ghostStatus.className = `status ${kind}`;
  els.ghostStatus.innerHTML = html;
}
function ghostError(msg) {
  ghostStatus("error", `<strong>Error:</strong> ${escapeHtml(msg)}`);
}
function setGhostLoading(loading) {
  els.ghostMerge.disabled = loading;
  els.pickGhostCsv.disabled = loading;
  els.ghostMerge.textContent = loading ? "Working…" : "Merge & Export";
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
els.modeGhost.addEventListener("click", () => showView("ghost"));
els.openTemplates.addEventListener("click", () => showView("templates"));
els.openCompanies.addEventListener("click", () => showView("companies"));

els.tmPickFile.addEventListener("click", tmPickFile);
els.tmRegister.addEventListener("click", tmRegister);

els.cmPickFile.addEventListener("click", cmPickFile);
els.cmRegister.addEventListener("click", cmRegister);
document.querySelectorAll("[data-nav]").forEach((b) =>
  b.addEventListener("click", () => showView(b.getAttribute("data-nav")))
);

els.pickXml.addEventListener("click", pickXml);
els.pickTemplate.addEventListener("click", pickTemplate);
els.intervalGenerate.addEventListener("click", intervalGenerate);

els.pickGhostCsv.addEventListener("click", pickGhostCsv);
els.ghostMerge.addEventListener("click", ghostMerge);

els.pickExcel.addEventListener("click", pickExcel);
els.browseFolder.addEventListener("click", browseFolder);
els.toWorkspace.addEventListener("click", toWorkspace);

els.config.addEventListener("change", refreshTemplateHint);
els.company.addEventListener("change", refreshCompanyHint);
els.generate.addEventListener("click", generate);

showView("mode");
