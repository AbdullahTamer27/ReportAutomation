// Inputs view: file/folder pickers, schematic-PDF pre-fill, and the step to
// the workspace.

import { els, pyapi, basename, hide, escapeHtml } from "./dom.js";
import { state } from "./state.js";
import { deriveConfigFromXml, computeDamageCount, previewConfig } from "./config.js";
import { setFieldValue } from "./fields.js";
import { ensureCompanies, resolveTemplate, refreshTemplateHint } from "./registry.js";
import { showView } from "./nav.js";

export async function pickExcel() {
  const api = pyapi();
  if (!api) return inputsError("Native file dialogs are only available in the desktop app.");
  const path = await api.pick_file(["Excel files (*.xlsx;*.xlsm)", "All files (*.*)"]);
  if (path) {
    state.excelPath = path;
    els.excelPath.textContent = path;
    els.excelPath.classList.remove("muted");
  }
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

// --- One-folder intake: pick a well folder, auto-discover every input --------
export async function openWellFolder() {
  const api = pyapi();
  if (!api) return inputsError("Native folder dialogs are only available in the desktop app.");
  const folder = await api.pick_folder();
  if (!folder) return;

  hide(els.inputsStatus);
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
    state.excelPath = data.excel_path;
    els.excelPath.textContent = data.excel_path;
    els.excelPath.classList.remove("muted");
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
  els.inputsSummary.textContent = `Excel: ${basename(state.excelPath)}  •  Folder: ${workingDir}`;
  showView("workspace");
  refreshTemplateHint();   // show the chosen template
  previewConfig();         // refresh the parsed-config preview (uses excelPath)
}

export function inputsError(msg) {
  els.inputsStatus.hidden = false;
  els.inputsStatus.className = "status error";
  els.inputsStatus.innerHTML = `<strong>Error:</strong> ${escapeHtml(msg)}`;
}
