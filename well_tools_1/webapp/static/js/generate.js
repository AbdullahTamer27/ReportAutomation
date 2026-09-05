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

// The buckets, in the order a person needs them: what stops the report, what
// deserves a look, what Talos already handled, and everything else.
const NOTE_GROUPS = [
  { cls: "note-error", label: "Must fix" },
  { cls: "note-warn", label: "Check" },
  { cls: "note-fix", label: "Talos fixed it" },
  { cls: "note-info", label: "Details" },
];

// The per-joint checks fire once per joint, so one rough string can push forty
// near-identical lines into the panel and bury the two notes that matter. They
// all share this shape, which is what lets them be folded together:
//   9 5/8" CSG joint 47: negative Wall Thickness (-0.03)
//   ^ subject           ^ joint  ^ detail
const JOINT_NOTE = /^(.+?)\s+joint\s+([^:]+):\s*(.+)$/i;

// Crude on purpose: two joints of the same kind differ only in their numbers,
// so blanking the numbers is enough to bucket them. Never shown to anyone —
// the label a person reads comes from commonLabel().
function kindKey(detail) {
  return detail.replace(/-?\d[\d.,]*/g, "#").replace(/\s+/g, " ").trim();
}

// What the notes in a group literally share, with whatever varies between them
// replaced by an ellipsis. Deriving the label from the notes themselves rather
// than from a table of known messages means a new check reads correctly here
// the day it is written, with nothing to keep in step.
//   "Max Loss 87.3% exceeds 100%"  ->  "Max Loss … exceeds 100%"
// Punctuation the varying tokens share is itself shared text, and dropping it
// leaves an ellipsis holding half a bracket — "(-0.03)" and "(-0.01)" must fold
// to "(…)", not "…)". Brackets lead, units and separators trail.
function shared(tokens, pattern) {
  const ends = tokens.map((t) => (String(t ?? "").match(pattern) || [""])[0]);
  return ends.every((e) => e === ends[0]) ? ends[0] : "";
}

function commonLabel(details) {
  if (details.length === 1) return details[0];
  const parts = details.map((d) => d.split(/(\s+)/));
  return parts[0]
    .map((token, i) => {
      if (parts.every((p) => p[i] === token)) return token;
      const varying = parts.map((p) => p[i]);
      return shared(varying, /^[([{]+/) + "…" + shared(varying, /[)\]}%,.;:]+$/);
    })
    .join("")
    .replace(/…(?:\s*…)+/g, "…")
    .replace(/\s{2,}/g, " ")
    .trim();
}

// One entry per distinct issue, each carrying the notes it stands for.
function rollup(notes) {
  const groups = new Map();
  for (const text of notes) {
    const m = text.match(JOINT_NOTE);
    // Only the per-joint checks repeat; everything else stands on its own.
    // JSON rather than concatenation: a subject and a kind joined by any
    // separator can collide once the separator appears inside either of them.
    const key = m ? JSON.stringify(["joint", m[1], kindKey(m[3])])
                  : JSON.stringify(["one", text]);
    let g = groups.get(key);
    if (!g) groups.set(key, (g = { subject: m ? m[1] : "", details: [], notes: [] }));
    g.details.push(m ? m[3] : text);
    g.notes.push(text);
  }
  return [...groups.values()].map((g) => ({
    notes: g.notes,
    label: g.notes.length === 1
      ? g.notes[0]
      : `${g.subject ? g.subject + " — " : ""}${commonLabel(g.details)}`,
  }));
}

function renderGroup(group, notes) {
  const rolled = rollup(notes);
  const items = rolled
    .map((item) => {
      const body = item.notes.length === 1
        ? escapeHtml(item.label)
        : `<details class="note-roll">
             <summary>${escapeHtml(item.label)}
               <span class="note-times">${item.notes.length}×</span></summary>
             <ul>${item.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>
           </details>`;
      return `<li class="${group.cls}">${body}</li>`;
    })
    .join("");
  // Only what blocks the report opens itself; the verdict above already says
  // the others are there, so they cost one line each until asked for.
  const open = group.cls === "note-error" ? " open" : "";
  return `<details class="notes-group"${open}>
      <summary>${group.label}<span class="notes-count">${rolled.length}</span></summary>
      <ul class="notes-list">${items}</ul>
    </details>`;
}

// One line, always visible, counting distinct issues rather than raw notes —
// "43 things to check" is true of forty joints on one string and useless.
function verdict(counts) {
  if (counts.error) {
    return ["note-error",
      `${counts.error} thing${counts.error === 1 ? "" : "s"} to fix before sending.`];
  }
  if (counts.warn) {
    return ["note-warn",
      `${counts.warn} thing${counts.warn === 1 ? "" : "s"} to check before sending.`];
  }
  if (counts.fix) {
    return ["note-fix",
      `Nothing to check — Talos corrected ${counts.fix} value${counts.fix === 1 ? "" : "s"}.`];
  }
  return ["note-ok", "Nothing to check."];
}

function renderNotes(notes) {
  if (!Array.isArray(notes) || notes.length === 0) return "";
  const buckets = new Map(NOTE_GROUPS.map((g) => [g.cls, []]));
  for (const n of notes) buckets.get(noteClass(n)).push(noteBody(n));

  const counts = {
    error: rollup(buckets.get("note-error")).length,
    warn: rollup(buckets.get("note-warn")).length,
    fix: rollup(buckets.get("note-fix")).length,
  };
  const [cls, text] = verdict(counts);
  const sections = NOTE_GROUPS
    .filter((g) => buckets.get(g.cls).length)
    .map((g) => renderGroup(g, buckets.get(g.cls)))
    .join("");

  return `<div class="notes-panel">
      <p class="notes-verdict ${cls}">${escapeHtml(text)}</p>
      ${sections}
    </div>`;
}

function showSuccess(data) {
  hide(els.status);   // result + notes now live on the right, above the preview
  els.previewPanel.hidden = false;
  els.previewResult.innerHTML =
    // The heading no longer counts anything — the verdict line inside the notes
    // does, from the same rollup, so the two can't disagree.
    `<div class="status success">
       <strong>Report created</strong>
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
