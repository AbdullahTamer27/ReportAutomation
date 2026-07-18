// Report generation, the result panel, and the PDF preview.

import { $, els, escapeHtml, hide, pyapi } from "./dom.js";
import { state } from "./state.js";
import { resolveTemplate, resolveCompany, configValue } from "./registry.js";
import { damageCountValue } from "./config.js";
import { collectFields, missingRequired } from "./fields.js";

export async function generate() {
  const template = resolveTemplate();
  if (!template) return showError("Please choose a report template (on the previous screen).");
  const company = resolveCompany();
  if (!company) return showError("Please choose a company (or add one in the Company Manager).");
  if (!configValue()) return showError("Please enter a configuration.");
  const workingDir = els.workingDirInput.value.trim();
  if (!state.excelPath) return showError("Excel data file is missing — go back and choose one.");
  if (!workingDir) return showError("Working directory is missing — go back and set one.");
  const miss = missingRequired();
  if (miss.length) {
    return showError(`Please fill required field${miss.length > 1 ? "s" : ""}: `
      + miss.map((f) => f.label).join(", ") + ".");
  }

  setLoading(true);
  showInfo("Generating report…");
  // Reset the right panel (previous result + preview) for this run.
  els.previewResult.innerHTML = "";
  els.previewBody.innerHTML = "";
  els.previewPanel.hidden = true;

  try {
    const res = await fetch("/api/report/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template_id: template.id,
        excel_path: state.excelPath,
        working_dir: workingDir,
        damage_count: damageCountValue(),
        company_id: company.id,
        include_disclaimer: els.includeDisclaimer.checked,
        wellhead_damage: els.wellheadDamage.checked,
        fw16: els.fw16.checked,
        xml_path: state.xmlPath || null,
        config: configValue() || null,
        // metadata fields (well_name, field, dates, …) from the registry-driven form
        fields: collectFields(),
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

export async function reveal(path) {
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
// The backend prefixes each note with a severity glyph. We read the severity
// from it, then drop it from the display text — the marker is redrawn in CSS
// (.notes-list li::before) so it stays monochrome and stays aligned.
const NOTE_SEVERITY = [
  ["❌", "note-error"],
  ["⚠", "note-warn"],
  ["✎", "note-fix"],
];

function noteClass(text) {
  const t = String(text).trim();
  const hit = NOTE_SEVERITY.find(([glyph]) => t.startsWith(glyph));
  return hit ? hit[1] : "note-info";
}

function noteBody(text) {
  const t = String(text).trim();
  const hit = NOTE_SEVERITY.find(([glyph]) => t.startsWith(glyph));
  // Trim the glyph plus any variation selector / spacing that follows it.
  return hit ? t.slice(hit[0].length).replace(/^[️\s]+/, "") : t;
}

function renderNotes(notes) {
  if (!Array.isArray(notes) || notes.length === 0) return "";
  const issues = notes.filter((n) => noteClass(n) !== "note-info").length;
  const items = notes
    .map((n) => `<li class="${noteClass(n)}">${escapeHtml(noteBody(n))}</li>`)
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
  hide(els.status);   // result + notes now live on the right, above the preview
  const issues = (data.notes || []).filter((n) => noteClass(n) !== "note-info").length;
  const heading = issues
    ? `Report created · ${issues} warning${issues === 1 ? "" : "s"}`
    : "Report created";
  els.previewPanel.hidden = false;
  els.previewResult.innerHTML =
    `<div class="status success">
       <strong>${heading}</strong>
       <div class="result-path">${escapeHtml(data.output_path)}</div>
       <button id="revealBtn" type="button" class="secondary">Reveal in file manager</button>
       ${renderNotes(data.notes)}
     </div>`;
  const btn = $("revealBtn");
  if (btn) btn.addEventListener("click", () => reveal(data.output_path));
  requestPreview(data.run_id);
}

export function setLoading(loading) {
  els.generate.disabled =
    loading || !resolveTemplate() || !resolveCompany() || !configValue() || !state.configOk;
  els.generate.textContent = loading ? "Working…" : "Generate Report";
}
