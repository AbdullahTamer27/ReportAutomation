// Vanilla ES module frontend — no framework, no build step.

const $ = (id) => document.getElementById(id);

const els = {
  damage: $("damageSelect"),
  template: $("templateSelect"),
  pickExcel: $("pickExcel"),
  excelPath: $("excelPath"),
  pickFolder: $("pickFolder"),
  folderPath: $("folderPath"),
  generate: $("generate"),
  status: $("status"),
};

const state = {
  templates: [],
  excelPath: null,
  workingDir: null,
};

// --- pywebview bridge -------------------------------------------------------
// window.pywebview.api is injected by the desktop shell. In a plain browser it
// won't exist, so the native pickers are unavailable there.
function pyapi() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

// --- Template registry ------------------------------------------------------
async function loadTemplates() {
  const res = await fetch("/api/templates");
  if (!res.ok) throw new Error(`Failed to load templates (HTTP ${res.status})`);
  state.templates = await res.json();
  populateDamageOptions();
}

function populateDamageOptions() {
  const counts = [...new Set(state.templates.map((t) => t.damage_count))].sort(
    (a, b) => a - b
  );
  els.damage.innerHTML = "";
  for (const c of counts) {
    const opt = document.createElement("option");
    opt.value = String(c);
    opt.textContent = `${c} joints`;
    els.damage.appendChild(opt);
  }
  populateTemplateOptions();
}

function populateTemplateOptions() {
  const dc = Number(els.damage.value);
  const matches = state.templates.filter((t) => t.damage_count === dc);
  els.template.innerHTML = "";
  for (const t of matches) {
    const opt = document.createElement("option");
    opt.value = String(t.id);
    opt.textContent = `${t.config_key} — ${t.name}`;
    els.template.appendChild(opt);
  }
}

function selectedTemplateId() {
  const v = els.template.value;
  return v ? Number(v) : null;
}

// --- Pickers ----------------------------------------------------------------
async function pickExcel() {
  const api = pyapi();
  if (!api) return showError("Native file dialogs are only available in the desktop app.");
  const path = await api.pick_file([
    "Excel files (*.xlsx;*.xlsm)",
    "All files (*.*)",
  ]);
  if (path) {
    state.excelPath = path;
    els.excelPath.textContent = path;
    els.excelPath.classList.remove("muted");
  }
}

async function pickFolder() {
  const api = pyapi();
  if (!api) return showError("Native folder dialogs are only available in the desktop app.");
  const path = await api.pick_folder();
  if (path) {
    state.workingDir = path;
    els.folderPath.textContent = path;
    els.folderPath.classList.remove("muted");
  }
}

// --- Generate ---------------------------------------------------------------
async function generate() {
  const templateId = selectedTemplateId();
  if (!templateId) return showError("Please choose a template.");
  if (!state.excelPath) return showError("Please choose an Excel data file.");
  if (!state.workingDir) return showError("Please choose a working directory.");

  setLoading(true);
  showInfo("Generating report…");

  try {
    const res = await fetch("/api/report/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template_id: templateId,
        excel_path: state.excelPath,
        working_dir: state.workingDir,
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      // FastAPI returns { detail: "..." } for HTTPException.
      const detail = data && data.detail ? data.detail : `HTTP ${res.status}`;
      showError(detail);
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
  if (!api) return;
  await api.reveal_file(path);
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
}

function setLoading(loading) {
  els.generate.disabled = loading;
  els.pickExcel.disabled = loading;
  els.pickFolder.disabled = loading;
  els.generate.textContent = loading ? "Working…" : "Generate Report";
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// --- Wire up ----------------------------------------------------------------
els.damage.addEventListener("change", populateTemplateOptions);
els.pickExcel.addEventListener("click", pickExcel);
els.pickFolder.addEventListener("click", pickFolder);
els.generate.addEventListener("click", generate);

loadTemplates().catch((err) => showError(err.message || String(err)));
