// DOM element references, small helpers, and the pywebview bridge.
// Imported by every feature module.

export const $ = (id) => document.getElementById(id);

export const els = {
  // mode
  modeReport: $("modeReport"),
  modeGhost: $("modeGhost"),
  // ghost merger
  ghostLength: $("ghostLength"),
  pickGhostCsv: $("pickGhostCsv"),
  ghostCsvPath: $("ghostCsvPath"),
  ghostMerge: $("ghostMerge"),
  ghostPickFolder: $("ghostPickFolder"),
  ghostStatus: $("ghostStatus"),
  ghostPreview: $("ghostPreview"),
  // report-automation sub-feature entry points (on the inputs view)
  openTemplates: $("openTemplates"),
  openCompanies: $("openCompanies"),
  // template manager
  tmPickFile: $("tmPickFile"),
  tmFilePath: $("tmFilePath"),
  tmName: $("tmName"),
  tmConfigKey: $("tmConfigKey"),
  tmRegister: $("tmRegister"),
  tmStatus: $("tmStatus"),
  tmList: $("tmList"),
  // company manager
  cmPickFile: $("cmPickFile"),
  cmFilePath: $("cmFilePath"),
  cmName: $("cmName"),
  cmRegister: $("cmRegister"),
  cmStatus: $("cmStatus"),
  cmList: $("cmList"),
  // topbar
  brandVersion: $("brandVersion"),
  // inputs
  openWellFolder: $("openWellFolder"),
  wellFolderHint: $("wellFolderHint"),
  pickExcel: $("pickExcel"),
  excelPath: $("excelPath"),
  workingDirInput: $("workingDirInput"),
  browseFolder: $("browseFolder"),
  pickXmlReport: $("pickXmlReport"),
  xmlReportPath: $("xmlReportPath"),
  damageAutoHint: $("damageAutoHint"),
  damageCountHint: $("damageCountHint"),
  templateSelect: $("templateSelect"),
  templatePickHint: $("templatePickHint"),
  toWorkspace: $("toWorkspace"),
  inputsStatus: $("inputsStatus"),
  // workspace
  inputsSummary: $("inputsSummary"),
  loadSchematic: $("loadSchematic"),
  schematicHint: $("schematicHint"),
  wellName: $("wellName"),
  fieldName: $("fieldName"),
  wellType: $("wellType"),
  btmDepth: $("btmDepth"),
  logDate: $("logDate"),
  origComp: $("origComp"),
  lastWko: $("lastWko"),
  configInput: $("configInput"),
  configPreview: $("configPreview"),
  company: $("companySelect"),
  damageCount: $("damageCount"),
  includeDisclaimer: $("includeDisclaimer"),
  wellheadDamage: $("wellheadDamage"),
  templateHint: $("templateHint"),
  companyHint: $("companyHint"),
  generate: $("generate"),
  status: $("status"),
  previewPanel: $("previewPanel"),
  previewMeta: $("previewMeta"),
  previewResult: $("previewResult"),
  previewBody: $("previewBody"),
};

// --- pywebview bridge -------------------------------------------------------
export function pyapi() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

// --- Helpers ----------------------------------------------------------------
export function hide(el) { el.hidden = true; }
export function basename(p) { return String(p).split(/[\\/]/).pop(); }
export function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
