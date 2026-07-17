// Configuration preview (parsed pipe model), XML-derived config, and the
// autonomous damage count.

import { els, escapeHtml } from "./dom.js";
import { state } from "./state.js";
import { configValue, updateGenerateEnabled } from "./registry.js";
import { fieldInput } from "./fields.js";

// --- Configuration preview --------------------------------------------------
let _cfgTimer = null;
export function scheduleConfigPreview() {
  clearTimeout(_cfgTimer);
  state.configOk = false;        // pending until the preview validates it
  _cfgTimer = setTimeout(previewConfig, 350);
  updateGenerateEnabled();
}

export async function previewConfig() {
  const cfg = configValue();
  if (!cfg) {
    els.configPreview.hidden = true;
    els.configPreview.innerHTML = "";
    state.configOk = false;
    updateGenerateEnabled();
    return;
  }
  try {
    const res = await fetch("/api/config/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: cfg, excel_path: state.excelPath, xml_path: state.xmlPath }),
    });
    const data = await res.json().catch(() => ({}));
    els.configPreview.hidden = false;
    if (!res.ok) {
      state.configOk = false;
      els.configPreview.className = "config-preview cfg-error";
      els.configPreview.innerHTML =
        `<strong>Can't parse:</strong> ${escapeHtml(data.detail || "HTTP " + res.status)}`;
      updateGenerateEnabled();
      return;
    }
    renderConfigPreview(data);
  } catch (err) {
    state.configOk = false;
    els.configPreview.hidden = false;
    els.configPreview.className = "config-preview cfg-error";
    els.configPreview.textContent = `Preview failed: ${err.message || err}`;
    updateGenerateEnabled();
  }
}

function renderConfigPreview(data) {
  // Case 1 (config > data): any configured pipe missing its Excel sheet blocks generate.
  const missing = data.pipes.filter((p) => p.sheet_found === false);
  state.configOk = missing.length === 0;

  els.configPreview.className = "config-preview" + (missing.length ? " cfg-error" : "");
  const items = data.pipes
    .map((p) => {
      if (p.sheet_found === false) {
        return `<li class="cfg-bad"><span class="cfg-role">${escapeHtml(p.role)}</span>
                ${escapeHtml(p.suffix)} <span class="cfg-dim">→ no “${escapeHtml(p.sheet)}” sheet in the workbook</span></li>`;
      }
      const joints = p.joint_count == null ? "" : ` · ${p.joint_count} joints`;
      const shoe = p.shoe_text ? ` · shoe ${escapeHtml(p.shoe_text)} ft` : "";
      return `<li><span class="cfg-role">${escapeHtml(p.role)}</span> ${escapeHtml(p.suffix)}
              <span class="cfg-dim">→ ${escapeHtml(p.sheet)}${joints}${shoe}</span></li>`;
    })
    .join("");
  const warns = (data.warnings || [])
    .map((w) => `<li class="cfg-warn">${escapeHtml(w)}</li>`)
    .join("");
  const blocked = missing.length
    ? `<div class="cfg-block">⛔ Configuration has ${data.pipes.length} pipe(s) but the workbook is
       missing ${missing.length} sheet(s). Fix the configuration or the Excel to generate.</div>`
    : "";
  els.configPreview.innerHTML =
    `<div class="cfg-title">${data.pipes.length} pipe${data.pipes.length === 1 ? "" : "s"}</div>
     <ul class="cfg-list">${items}${warns}</ul>${blocked}`;
  updateGenerateEnabled();
  if (state.configOk) computeDamageCount();   // refresh the auto damage count
  // Auto-fill Bottom depth from the XML's deepest point (until the user edits it).
  const btm = fieldInput("btm_depth");
  if (data.bottom_depth && btm &&
      (!btm.value || btm.classList.contains("prefilled"))) {
    btm.value = data.bottom_depth;
    btm.classList.add("prefilled");
  }
}

export function damageCountValue() {
  const n = parseInt(els.damageCount.value, 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

// --- WellSchematic XML → config + autonomous damage count --------------------
export async function deriveConfigFromXml() {
  if (!state.xmlPath || !els.configInput) return computeDamageCount();
  try {
    const res = await fetch("/api/config/from-xml", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ xml_path: state.xmlPath }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.config) {
      els.configInput.value = data.config;
      els.configInput.classList.add("prefilled");
      if (els.damageAutoHint) {
        els.damageAutoHint.textContent = `Configuration set from the schematic: ${data.config} — review it.`;
        els.damageAutoHint.classList.remove("hint-warn");
      }
      scheduleConfigPreview();   // validates + auto damage count + bottom depth
    } else {
      computeDamageCount();      // couldn't derive — use whatever config is there
    }
  } catch (err) {
    computeDamageCount();
  }
}

export async function computeDamageCount() {
  // Needs the XML, the Excel, and a validated config (pipe sheets resolve).
  if (!state.xmlPath || !state.excelPath || !configValue() || !state.configOk) return;
  els.damageCountHint.textContent = "Computing damage count…";
  els.damageCountHint.classList.remove("hint-warn");
  try {
    const res = await fetch("/api/damage/count", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ xml_path: state.xmlPath, excel_path: state.excelPath, config: configValue() }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      els.damageCountHint.textContent = data.detail || `Couldn't compute (HTTP ${res.status})`;
      els.damageCountHint.classList.add("hint-warn");
      return;
    }
    els.damageCount.value = String(data.count);
    els.damageCount.classList.add("prefilled");
    const warn = (data.warnings && data.warnings.length) ? "  ⚠ " + data.warnings.join("  ") : "";
    els.damageCountHint.textContent =
      `Auto-set to ${data.count} from the schematic — worst Class C/D per pipe per interval. Override if needed.${warn}`;
    els.damageCountHint.classList.toggle("hint-warn", !!warn);
  } catch (err) {
    els.damageCountHint.textContent = err.message || String(err);
    els.damageCountHint.classList.add("hint-warn");
  }
}
