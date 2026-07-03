// Shared front-end state (module singletons).

export const state = {
  templates: [],
  templatesLoaded: false,
  companies: [],
  companiesLoaded: false,
  excelPath: null,
  xmlPath: null,     // optional WellSchematic XML → autonomous damage count
  configOk: false,   // config parsed AND every configured pipe has its Excel sheet
};

export const ghostState = { csvPath: null };
export const tmState = { filePath: null };
export const cmState = { filePath: null };
