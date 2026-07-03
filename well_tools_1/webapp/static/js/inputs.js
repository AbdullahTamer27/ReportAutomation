// Inputs view: file/folder pickers, schematic-PDF pre-fill, and the step to
// the workspace.

import { els, pyapi, basename, hide, escapeHtml } from "./dom.js";
import { state } from "./state.js";
import { deriveConfigFromXml, computeDamageCount, previewConfig } from "./config.js";
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
export const SCHEMATIC_FIELDS = {   // response key -> input element
  well_name: "wellName",
  well_type: "wellType",
  orig_comp: "origComp",
  last_wko: "lastWko",
};

function schematicHintMsg(text, warn) {
  els.schematicHint.textContent = text;
  els.schematicHint.classList.toggle("hint-warn", !!warn);
}

export async function pickSchematic() {
  const api = pyapi();
  if (!api) return schematicHintMsg("Native file dialogs are only available in the desktop app.", true);
  const path = await api.pick_file(["PDF files (*.pdf)", "All files (*.*)"]);
  if (!path) return;
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
    for (const [key, elId] of Object.entries(SCHEMATIC_FIELDS)) {
      const val = data.fields ? data.fields[key] : undefined;
      if (val) {
        const input = els[elId];
        input.value = val;
        input.classList.add("prefilled");        // highlight for review
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
