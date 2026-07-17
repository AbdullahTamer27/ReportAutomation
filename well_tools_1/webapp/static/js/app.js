// Talos front-end entry point — vanilla ES modules, no build step.
// Imports the feature modules and wires up all event listeners in one place.

import { els } from "./dom.js";
import { showView } from "./nav.js";
import { ensureTemplates, refreshTemplateHint, refreshCompanyHint } from "./registry.js";
import { scheduleConfigPreview } from "./config.js";
import {
  openWellFolder, pickExcel, browseFolder, pickXmlReport, pickSchematic, toWorkspace,
  inputsError,
} from "./inputs.js";
import { refreshFields } from "./fields.js";
import { generate } from "./generate.js";
import { tmPickFile, tmRegister, cmPickFile, cmRegister } from "./managers.js";
import { pickGhostCsv, ghostMerge, ghostMergeFolder } from "./ghost.js";
import { checkForUpdates } from "./updater.js";

// --- Mode selection + navigation --------------------------------------------
els.modeReport.addEventListener("click", () => {
  showView("inputs");
  ensureTemplates().catch((err) => inputsError(err.message || String(err)));
});
els.modeGhost.addEventListener("click", () => showView("ghost"));
els.openTemplates.addEventListener("click", () => showView("templates"));
els.openCompanies.addEventListener("click", () => showView("companies"));
document.querySelectorAll("[data-nav]").forEach((b) =>
  b.addEventListener("click", () => showView(b.getAttribute("data-nav")))
);

// --- Managers ---------------------------------------------------------------
els.tmPickFile.addEventListener("click", tmPickFile);
els.tmRegister.addEventListener("click", tmRegister);
els.cmPickFile.addEventListener("click", cmPickFile);
els.cmRegister.addEventListener("click", cmRegister);

// --- Ghost Merger -----------------------------------------------------------
els.pickGhostCsv.addEventListener("click", pickGhostCsv);
els.ghostMerge.addEventListener("click", ghostMerge);
els.ghostPickFolder.addEventListener("click", ghostMergeFolder);

// --- Inputs view ------------------------------------------------------------
els.openWellFolder.addEventListener("click", openWellFolder);
els.pickExcel.addEventListener("click", pickExcel);
els.browseFolder.addEventListener("click", browseFolder);
els.pickXmlReport.addEventListener("click", pickXmlReport);
els.loadSchematic.addEventListener("click", pickSchematic);
els.toWorkspace.addEventListener("click", toWorkspace);

// --- Workspace form ---------------------------------------------------------
els.templateSelect.addEventListener("change", () => {
  refreshTemplateHint();
  refreshFields(els.metaFields, els.templateSelect.value || null);   // form follows the template
});
els.configInput.addEventListener("input", scheduleConfigPreview);
els.configInput.addEventListener("input", () => els.configInput.classList.remove("prefilled"));
els.company.addEventListener("change", refreshCompanyHint);
els.generate.addEventListener("click", generate);

// Damage count clears its own auto-fill highlight (registry fields handle their
// own clear-on-edit inside fields.js when rendered).
els.damageCount.addEventListener("input", () => {
  els.damageCount.classList.remove("prefilled");
  els.damageCountHint.textContent = "";
});

// --- Boot -------------------------------------------------------------------
showView("mode");
refreshFields(els.metaFields);   // build the metadata form (full registry until a template is chosen)
checkForUpdates();   // non-blocking: banner / required modal / blocked screen

// Show the running version beside the brand name (from the local server).
fetch("/api/health")
  .then((r) => r.json())
  .then((d) => {
    if (d && d.version && els.brandVersion) {
      els.brandVersion.textContent = `v${d.version}`;
      els.brandVersion.hidden = false;
    }
  })
  .catch(() => {});   // header just omits the version if it can't be read
