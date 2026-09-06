// Inputs view: file/folder pickers, schematic-PDF pre-fill, and the step to
// the workspace.

import { els, pyapi, basename, hide, escapeHtml } from "./dom.js";
import { state } from "./state.js";
import { deriveConfigFromXml, computeDamageCount, previewConfig } from "./config.js";
import { setFieldValue, clearFields } from "./fields.js";
import {
  ensureCompanies, resolveTemplate, refreshTemplateHint, updateGenerateEnabled,
} from "./registry.js";
import { showView } from "./nav.js";

// Parsing the workbook is the one slow step between choosing the inputs and
// using the form, and it does not depend on anything chosen after it. Starting
// it the moment the file is known means it is done by the time the form asks —
// the user spends that time filling in the rest. Deliberately not awaited: it
// is an optimisation, and nothing waits on it or reports it failing.
function warmWorkbook(path) {
  if (!path) return;
  fetch("/api/workbook/warm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ excel_path: path }),
  }).catch(() => {});
}

function setExcelPath(path) {
  state.excelPath = path;
  els.excelPath.textContent = path;
  els.excelPath.classList.remove("muted");
  warmWorkbook(path);
}

export async function pickExcel() {
  const api = pyapi();
  if (!api) return inputsError("Native file dialogs are only available in the desktop app.");
  const path = await api.pick_file(["Excel files (*.xlsx;*.xlsm)", "All files (*.*)"]);
  if (path) setExcelPath(path);
}

export async function browseFolder() {
  const api = pyapi();
  if (!api) return inputsError("Native folder dialogs are only available in the desktop app.");
  const path = await api.pick_folder();
  if (path) els.workingDirInput.value = path;
}

function wellFolderHint(text, warn) {
  els.wellFolderHint.textContent = text;
  els.wellFolderHint.classList.toggle("hint-warn", !!warn);
}

// The schematic hint's resting wording lives in index.html. Read once at load so
// the reset restores what the markup actually says, rather than a copy of it
// here that would quietly drift the first time the sentence is reworded.
const SCHEMATIC_HINT = els.schematicHint ? els.schematicHint.textContent : "";

// Opening a well folder starts a new report, so nothing from the last one may
// survive into it. The scan only ever *fills in what it finds*, which on its own
// is silently wrong the second time round: a folder with no XML would keep the
// previous well's configuration, and one with no workbook would generate the new
// report from the previous well's data. Clearing first makes anything the new
// folder lacks visibly absent instead.
function resetWell() {
  state.excelPath = null;
  state.xmlPath = null;
  state.configOk = false;

  els.excelPath.textContent = "No file selected";
  els.excelPath.classList.add("muted");
  if (els.xmlReportPath) {
    els.xmlReportPath.textContent = "No file selected";
    els.xmlReportPath.classList.add("muted");
  }

  els.configInput.value = "";
  els.configInput.classList.remove("prefilled");
  els.configPreview.hidden = true;
  els.configPreview.innerHTML = "";

  els.damageCount.value = "0";
  els.damageCount.classList.remove("prefilled");
  els.damageCountHint.textContent = "";

  schematicHintMsg(SCHEMATIC_HINT, false);
  clearFields();
  hide(els.inputsStatus);

  // The workspace is a different view, so it keeps the previous report's result
  // banner and rendered pages until something clears them. Going back for
  // another well and returning would otherwise show the last well's preview.
  els.previewPanel.hidden = true;
  els.previewResult.innerHTML = "";
  els.previewBody.innerHTML = "";

  updateGenerateEnabled();
}

// --- One-folder intake: pick a well folder, auto-discover every input --------
export async function openWellFolder() {
  const api = pyapi();
  if (!api) return inputsError("Native folder dialogs are only available in the desktop app.");
  const folder = await api.pick_folder();
  if (!folder) return;

  resetWell();
  wellFolderHint("Scanning folder…", false);
  let data;
  try {
    const res = await fetch("/api/well-folder/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_path: folder }),
    });
    data = await res.json().catch(() => ({}));
    if (!res.ok) return wellFolderHint(data.detail || `Scan failed (HTTP ${res.status})`, true);
  } catch (err) {
    return wellFolderHint(err.message || String(err), true);
  }

  // The working directory is the folder itself (its IMGS/ holds the images).
  els.workingDirInput.value = data.working_dir || folder;

  if (data.excel_path) {
    setExcelPath(data.excel_path);        // starts the workbook parse in the background
  }
  if (data.xml_path) {
    state.xmlPath = data.xml_path;
    if (els.xmlReportPath) {
      els.xmlReportPath.textContent = data.xml_path;
      els.xmlReportPath.classList.remove("muted");
    }
    await deriveConfigFromXml();          // fills Configuration + auto damage count
  }
  if (data.schematic_pdf) {
    await loadSchematicFromPath(data.schematic_pdf);   // fills well name/type/dates
  }

  const found = (data.found || []).join(", ") || "nothing";
  const missing = data.missing || [];
  wellFolderHint(
    `Found: ${found}.` +
    (missing.length ? `  Missing: ${missing.join(", ")} — set those manually below.` : ""),
    missing.length > 0,
  );
}

// --- WellSchematic XML → autonomous damage count ----------------------------
export async function pickXmlReport() {
  const api = pyapi();
  if (!api) return inputsError("Native file dialogs are only available in the desktop app.");
  const path = await api.pick_file(["WellSchematic XML (*.xml)", "All files (*.*)"]);
  if (!path) return;
  state.xmlPath = path;
  if (els.xmlReportPath) {
    els.xmlReportPath.textContent = path;
    els.xmlReportPath.classList.remove("muted");
  }
  await deriveConfigFromXml();   // pre-fill Configuration, then preview it
}

// --- Load optional fields from a well-schematic PDF -------------------------
// Registry keys the schematic PDF can pre-fill (the parser returns these keys).
export const SCHEMATIC_FIELDS = ["well_name", "well_type", "orig_comp", "last_wko"];

function schematicHintMsg(text, warn) {
  els.schematicHint.textContent = text;
  els.schematicHint.classList.toggle("hint-warn", !!warn);
}

export async function pickSchematic() {
  const api = pyapi();
  if (!api) return schematicHintMsg("Native file dialogs are only available in the desktop app.", true);
  const path = await api.pick_file(["PDF files (*.pdf)", "All files (*.*)"]);
  if (!path) return;
  return loadSchematicFromPath(path);
}

// Parse a schematic PDF at `path` and pre-fill the optional metadata fields.
// Shared by the manual picker and the one-folder intake.
export async function loadSchematicFromPath(path) {
  schematicHintMsg(`Reading ${basename(path)}…`, false);
  try {
    const res = await fetch("/api/schematic/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pdf_path: path }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return schematicHintMsg(data.detail || `Parse failed (HTTP ${res.status})`, true);

    const filled = [];
    for (const key of SCHEMATIC_FIELDS) {
      const val = data.fields ? data.fields[key] : undefined;
      if (val && setFieldValue(key, val)) {       // sets value + bronze highlight
        filled.push(key.replace("_", " "));
      }
    }
    if (!filled.length) {
      schematicHintMsg("No fields could be read from that PDF.", true);
    } else {
      const warn = (data.warnings && data.warnings.length)
        ? "  ⚠ " + data.warnings.join("  ") : "";
      schematicHintMsg(`Loaded ${filled.length} field(s): ${filled.join(", ")} — review/edit before generating.${warn}`,
                       !!warn);
    }
  } catch (err) {
    schematicHintMsg(err.message || String(err), true);
  }
}

export async function toWorkspace() {
  const workingDir = els.workingDirInput.value.trim();
  if (!state.excelPath) return inputsError("Please choose an Excel data file.");
  if (!workingDir) return inputsError("Please provide a working directory.");
  if (!resolveTemplate()) return inputsError("Please choose a report template.");

  hide(els.inputsStatus);
  try {
    await ensureCompanies();
  } catch (err) {
    return inputsError(err.message || String(err));
  }
  showView("workspace");
  refreshTemplateHint();   // show the chosen template
  previewConfig();         // refresh the parsed-config preview (uses excelPath)
}

export function inputsError(msg) {
  els.inputsStatus.hidden = false;
  els.inputsStatus.className = "status error";
  els.inputsStatus.innerHTML = `<strong>Error:</strong> ${escapeHtml(msg)}`;
}
