// Epic C — render the metadata form from the field registry (/api/fields), and
// read/write those fields by their registry key. The form is no longer hardcoded
// in index.html; it's generated here from whatever the registry (and later, the
// selected template) declares.

import { escapeHtml } from "./dom.js";

let FIELDS = [];
let CONTROLS = [];   // [{key, section_id, present}] — checkbox/damage-count gating

export async function loadFields(templateId) {
  const url = templateId
    ? `/api/fields?template_id=${encodeURIComponent(templateId)}`
    : "/api/fields";
  try {
    const res = await fetch(url);
    const data = await res.json();
    FIELDS = (data && data.fields) || [];
    CONTROLS = (data && data.controls) || [];
  } catch (_e) {
    FIELDS = [];
    CONTROLS = [];
  }
  return FIELDS;
}

// Show/hide the non-text controls (disclaimer, well-head, FW16, damage count)
// based on whether the chosen template contains each one's tag.
function applyControls() {
  for (const c of CONTROLS) {
    const sec = document.getElementById(c.section_id);
    // Inline display (not the `hidden` attribute): `.field { display:flex }` is a
    // class selector and would otherwise beat `[hidden]`'s display:none.
    if (sec) sec.style.display = c.present ? "" : "none";
  }
}

// Re-render the form for a template (or the full registry when templateId is
// falsy), preserving any values the user already typed.
export async function refreshFields(container, templateId) {
  const prev = collectFields();          // capture current values (old FIELDS)
  await loadFields(templateId);          // FIELDS now matches the template
  renderFields(container);
  applyControls();                       // show/hide checkboxes + damage count
  for (const f of FIELDS) {
    const v = prev[f.key];
    if (v != null && v !== "") {
      const el = document.getElementById(f.dom_id);
      if (el) el.value = v;
    }
  }
}

function fieldSection(f) {
  const sec = document.createElement("section");
  sec.className = "field";
  const cls = "text-input" + (f.mono ? " mono" : "");
  const mark = f.required
    ? ' <span class="req" aria-hidden="true">*</span>'
    : ' <span class="opt">(optional)</span>';
  sec.innerHTML =
    `<label for="${f.dom_id}">${escapeHtml(f.label)}${mark}</label>` +
    `<input type="text" id="${f.dom_id}" class="${cls}"${f.required ? " aria-required=\"true\"" : ""} ` +
    `placeholder="${escapeHtml(f.placeholder || "")}" autocomplete="off" />`;
  // Auto-fill / error highlights clear once the user edits the field themselves.
  const input = sec.querySelector("input");
  input.addEventListener("input", () => input.classList.remove("prefilled", "field-error"));
  return sec;
}

function pairInto(container, fs) {
  let i = 0;
  while (i < fs.length) {
    const f = fs[i], next = fs[i + 1];
    if (f.width === "half" && next && next.width === "half") {
      const row = document.createElement("div");
      row.className = "field-row";
      row.append(fieldSection(f), fieldSection(next));
      container.appendChild(row);
      i += 2;
    } else {
      container.appendChild(fieldSection(f));
      i += 1;
    }
  }
}

// Render the fields into `container`, one section-label heading per group (in
// first-seen order), pairing consecutive half-width fields within each group.
export function renderFields(container) {
  if (!container) return;
  container.innerHTML = "";
  const order = [];
  const byGroup = new Map();
  for (const f of FIELDS) {
    if (!byGroup.has(f.group)) { byGroup.set(f.group, []); order.push(f.group); }
    byGroup.get(f.group).push(f);
  }
  for (const g of order) {
    if (g) {
      const h = document.createElement("p");
      h.className = "section-label";
      h.textContent = g;
      container.appendChild(h);
    }
    pairInto(container, byGroup.get(g));
  }
}

// Required fields left empty — for the Generate guard. Also flags them red.
export function missingRequired() {
  const missing = [];
  for (const f of FIELDS) {
    if (!f.required) continue;
    const el = document.getElementById(f.dom_id);
    if (!el || !el.value.trim()) {
      if (el) el.classList.add("field-error");
      missing.push(f);
    }
  }
  return missing;
}

export function fieldInput(key) {
  const f = FIELDS.find((x) => x.key === key);
  return f ? document.getElementById(f.dom_id) : null;
}

// { key: trimmed value | null } for the generate payload.
export function collectFields() {
  const out = {};
  for (const f of FIELDS) {
    const el = document.getElementById(f.dom_id);
    out[f.key] = (el && el.value.trim()) || null;
  }
  return out;
}

// Empty every rendered field and drop its auto-fill highlight. Used when a new
// well folder is opened: the values on screen describe the previous well, and a
// schematic that fills only some of them would otherwise leave the two mixed.
export function clearFields() {
  for (const f of FIELDS) {
    const el = document.getElementById(f.dom_id);
    if (!el) continue;
    el.value = "";
    el.classList.remove("prefilled", "field-error");
  }
}

// Set a field's value and flag it as auto-filled (bronze) for review.
export function setFieldValue(key, value) {
  const el = fieldInput(key);
  if (!el) return false;
  el.value = value;
  el.classList.add("prefilled");
  return true;
}
