// Epic C — render the metadata form from the field registry (/api/fields), and
// read/write those fields by their registry key. The form is no longer hardcoded
// in index.html; it's generated here from whatever the registry (and later, the
// selected template) declares.

import { escapeHtml } from "./dom.js";

let FIELDS = [];

export async function loadFields() {
  try {
    const res = await fetch("/api/fields");
    const data = await res.json();
    FIELDS = (data && data.fields) || [];
  } catch (_e) {
    FIELDS = [];
  }
  return FIELDS;
}

function fieldSection(f) {
  const sec = document.createElement("section");
  sec.className = "field";
  const cls = "text-input" + (f.mono ? " mono" : "");
  const opt = f.required ? "" : ' <span class="opt">(optional)</span>';
  sec.innerHTML =
    `<label for="${f.dom_id}">${escapeHtml(f.label)}${opt}</label>` +
    `<input type="text" id="${f.dom_id}" class="${cls}" ` +
    `placeholder="${escapeHtml(f.placeholder || "")}" autocomplete="off" />`;
  // Auto-fill highlight clears once the user edits the field themselves.
  const input = sec.querySelector("input");
  input.addEventListener("input", () => input.classList.remove("prefilled"));
  return sec;
}

// Render the fields into `container`, pairing consecutive half-width fields into
// a .field-row (reproducing today's side-by-side layout).
export function renderFields(container) {
  if (!container) return;
  container.innerHTML = "";
  let i = 0;
  while (i < FIELDS.length) {
    const f = FIELDS[i];
    const next = FIELDS[i + 1];
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

// Set a field's value and flag it as auto-filled (bronze) for review.
export function setFieldValue(key, value) {
  const el = fieldInput(key);
  if (!el) return false;
  el.value = value;
  el.classList.add("prefilled");
  return true;
}
